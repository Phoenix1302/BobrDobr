package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"os"
	"os/exec"
	"os/signal"
	"path/filepath"
	"runtime"
	"strings"
	"sync"
	"syscall"
	"time"

	"github.com/Phoenix1302/BobrDobr/pkg/config"
	"github.com/Phoenix1302/BobrDobr/pkg/crash"
	"github.com/Phoenix1302/BobrDobr/pkg/gui"
	"github.com/Phoenix1302/BobrDobr/pkg/logger"
	"github.com/Phoenix1302/BobrDobr/pkg/netadapter"
	"github.com/Phoenix1302/BobrDobr/pkg/singleinstance"
	"github.com/Phoenix1302/BobrDobr/pkg/subscription"
	"github.com/Phoenix1302/BobrDobr/pkg/tray"
	"github.com/Phoenix1302/BobrDobr/pkg/updater"
	"github.com/Phoenix1302/BobrDobr/pkg/vpn"
)

func getAppDataDir() string {
	// 1. Standard Windows User Profile AppData (Roaming) for user config
	appData := os.Getenv("APPDATA")
	if appData == "" {
		appData = os.Getenv("LOCALAPPDATA")
	}
	if appData == "" {
		home, _ := os.UserHomeDir()
		appData = filepath.Join(home, "AppData", "Roaming")
	}
	dir := filepath.Join(appData, "BobrDobr")
	_ = os.MkdirAll(dir, 0700)

	// 2. Seamless Migration: If Roaming has no settings.json yet, check LocalAppData for existing config
	roamingSettings := filepath.Join(dir, "settings.json")
	if _, err := os.Stat(roamingSettings); os.IsNotExist(err) {
		localAppData := os.Getenv("LOCALAPPDATA")
		if localAppData != "" {
			localSettings := filepath.Join(localAppData, "BobrDobr", "settings.json")
			if _, err := os.Stat(localSettings); err == nil {
				data, err := os.ReadFile(localSettings)
				if err == nil && len(data) > 0 {
					_ = os.WriteFile(roamingSettings, data, 0600)
				}
			}
		}
	}

	return dir
}

func findBinaryPath(name string) string {
	exePath, _ := os.Executable()
	exeDir := filepath.Dir(exePath)

	progFiles := os.Getenv("ProgramFiles")
	if progFiles == "" {
		progFiles = `C:\Program Files`
	}

	appData := os.Getenv("LOCALAPPDATA")
	if appData == "" {
		home, _ := os.UserHomeDir()
		appData = filepath.Join(home, "AppData", "Local")
	}

	candidates := []string{
		filepath.Join(exeDir, "bin", name),
		filepath.Join(exeDir, name),
		filepath.Join(progFiles, "BobrDobr", "bin", name),
		filepath.Join(progFiles, "BobrDobr", name),
		filepath.Join(appData, "Programs", "BobrDobr", "bin", name),
		filepath.Join(appData, "Programs", "BobrDobr", name),
		filepath.Join("bin", name),
		filepath.Join("bin", "windows", name),
	}
	for _, c := range candidates {
		if _, err := os.Stat(c); err == nil {
			abs, _ := filepath.Abs(c)
			return abs
		}
	}
	return name
}

func buildAmneziaWGConfigText(cfg *config.AmneziaWGConfig) string {
	if cfg == nil {
		return ""
	}
	var sb strings.Builder
	sb.WriteString("[Interface]\n")
	if cfg.Address != "" {
		sb.WriteString(fmt.Sprintf("Address = %s\n", cfg.Address))
	}
	if cfg.PrivateKey != "" {
		sb.WriteString(fmt.Sprintf("PrivateKey = %s\n", cfg.PrivateKey))
	}
	if cfg.DNS != "" {
		sb.WriteString(fmt.Sprintf("DNS = %s\n", cfg.DNS))
	}
	if cfg.Jc > 0 {
		sb.WriteString(fmt.Sprintf("Jc = %d\n", cfg.Jc))
	}
	if cfg.Jmin > 0 {
		sb.WriteString(fmt.Sprintf("Jmin = %d\n", cfg.Jmin))
	}
	if cfg.Jmax > 0 {
		sb.WriteString(fmt.Sprintf("Jmax = %d\n", cfg.Jmax))
	}
	if cfg.S1 > 0 {
		sb.WriteString(fmt.Sprintf("S1 = %d\n", cfg.S1))
	}
	if cfg.S2 > 0 {
		sb.WriteString(fmt.Sprintf("S2 = %d\n", cfg.S2))
	}
	if cfg.H1 > 0 {
		sb.WriteString(fmt.Sprintf("H1 = %d\n", cfg.H1))
	}
	if cfg.H2 > 0 {
		sb.WriteString(fmt.Sprintf("H2 = %d\n", cfg.H2))
	}
	if cfg.H3 > 0 {
		sb.WriteString(fmt.Sprintf("H3 = %d\n", cfg.H3))
	}
	if cfg.H4 > 0 {
		sb.WriteString(fmt.Sprintf("H4 = %d\n", cfg.H4))
	}

	sb.WriteString("\n[Peer]\n")
	if cfg.PublicKey != "" {
		sb.WriteString(fmt.Sprintf("PublicKey = %s\n", cfg.PublicKey))
	}
	if cfg.PresharedKey != "" {
		sb.WriteString(fmt.Sprintf("PresharedKey = %s\n", cfg.PresharedKey))
	}
	if cfg.Endpoint != "" {
		sb.WriteString(fmt.Sprintf("Endpoint = %s\n", cfg.Endpoint))
	}
	if cfg.AllowedIPs != "" {
		sb.WriteString(fmt.Sprintf("AllowedIPs = %s\n", cfg.AllowedIPs))
	}
	return sb.String()
}

func main() {
	defer func() {
		if r := recover(); r != nil {
			crash.HandleCrash(r, "Top-level main()")
			os.Exit(1)
		}
	}()

	// 0. Initialize robust persistent file logging with automatic rotation and safe stdout fallback
	appDir := getAppDataDir()
	logWriter, err := logger.Setup(appDir, "1.2.2")
	if err == nil {
		defer logWriter.Close()
	}
	configPath := filepath.Join(appDir, "settings.json")

	// 0a. Purge leftover installers from previous updates to prevent disk clutter
	if err := updater.CleanupOldInstallers(); err != nil {
		log.Printf("[ОБНОВЛЕНИЕ] Очистка старых файлов установки: %v", err)
	}

	// 0b. Protect host GUI process from accidental console termination (CTRL_C / CTRL_BREAK / SIGTERM)
	sigCh := make(chan os.Signal, 2)
	signal.Notify(sigCh, os.Interrupt, syscall.SIGTERM)
	go func() {
		defer crash.Recover("Signal watcher")
		for sig := range sigCh {
			log.Printf("[БОБР] Перехвачен консольный сигнал %v: игнорируется в GUI процессе для стабильности", sig)
		}
	}()

	// 0c. Guarantee UAC elevation for Wintun and network route management
	if !gui.IsElevated() {
		if err := gui.RelaunchAsAdmin(); err == nil {
			os.Exit(0)
		}
		log.Printf("[ВНИМАНИЕ] Не удалось автоматически повысить привилегии: продолжение работы")
	}

	log.Println("[БОБР] Запуск BobrDobr VPN v1.2.2 (Go Native Engine)...")

	// 1. Single Instance Protection & Named Pipe IPC
	instance := singleinstance.New(singleinstance.DefaultMutexName, singleinstance.DefaultPipeName)
	acquired, err := instance.TryAcquire()
	if err != nil {
		log.Printf("[ПРОТЕЧКА] Ошибка проверки единственного экземпляра: %v", err)
	}

	// 2. Initialize encrypted configuration store
	store, err := config.NewStore(configPath)
	if err != nil {
		log.Printf("[ПРОТЕЧКА] Ошибка загрузки хранилища конфигураций: %v", err)
	}

	// 3. Initialize Adapter Manager (Ping-Pong rotation bobr0 <-> bobr1)
	adapterMgr := netadapter.NewAdapterManager()

	// 3b. Initialize Host Routing Exceptions Manager
	routeMgr := vpn.NewRouteManager()

	// 4. Initialize Windows Job Object for bulletproof child process termination
	jobObject, err := vpn.NewJobObject()
	if err != nil {
		log.Printf("[ПРОТЕЧКА] Предупреждение JobObject: %v", err)
	}
	if jobObject != nil {
		defer jobObject.Close()
	}

	// Locate binary engines
	amneziaBin := findBinaryPath("amneziawg-go.exe")
	openconnectBin := findBinaryPath("openconnect.exe")
	wintunDll := findBinaryPath("wintun.dll")
	vpncScript := findBinaryPath("vpnc-script-win.js")

	// Whitelist VPN engines in Windows Defender Firewall (in background, non-blocking)
	go func() {
		defer crash.Recover("Firewall rules initialization")
		ensureFirewallRule("BobrDobr AmneziaWG", amneziaBin)
		ensureFirewallRule("BobrDobr OpenConnect", openconnectBin)
	}()

	amneziaSup := vpn.NewAmneziaSupervisor(amneziaBin, jobObject)
	openconnectSup := vpn.NewOpenConnectSupervisor(openconnectBin, jobObject)

	// 5. Initialize GUI (Spacious Desktop Window)
	ui := gui.NewGUI("БобрДобр VPN", 920, 820)

	// Check for --minimized / -minimized startup argument (start hidden to tray)
	startMinimized := false
	for _, arg := range os.Args[1:] {
		if strings.EqualFold(arg, "--minimized") || strings.EqualFold(arg, "-minimized") {
			startMinimized = true
			break
		}
	}

	var minimizedOnce sync.Once
	hideIfMinimized := func() {
		if startMinimized {
			minimizedOnce.Do(func() {
				ui.Hide()
			})
		}
	}

	if startMinimized {
		log.Println("[БОБР] Запуск в фоновом режиме (--minimized): окно будет скрыто в системный трей")
		go func() {
			defer crash.Recover("Startup minimized watcher")
			for i := 0; i < 100; i++ {
				time.Sleep(30 * time.Millisecond)
				if ui.IsVisible() {
					hideIfMinimized()
					break
				}
			}
		}()
	}

	// If another instance is running, activate it or show conflict dialog
	if !acquired {
		log.Println("[БОБР] Обнаружен работающий экземпляр BobrDobr VPN.")
		resp, pingErr := instance.SendMessage(singleinstance.MsgPing, 2*time.Second)
		if pingErr == nil && resp == singleinstance.RespPong {
			log.Println("[БОБР] Активный экземпляр откликнулся на PING. Вывод на передний план...")
			_, _ = instance.SendMessage(singleinstance.MsgActivate, 2*time.Second)
			time.Sleep(300 * time.Millisecond)
			os.Exit(0)
		} else {
			log.Printf("[ВНИМАНИЕ] Другой процесс удерживает блокировку, но не отвечает: %v", pingErr)
		}
	}

	// Start IPC server to listen for future conflict / activation signals
	ipcCtx, cancelIPC := context.WithCancel(context.Background())
	defer cancelIPC()

	_ = instance.StartIPCServer(ipcCtx, func(msg string) (string, error) {
		log.Printf("[БОБР] Получена IPC команда: %s", msg)
		switch msg {
		case singleinstance.MsgPing:
			return singleinstance.RespPong, nil
		case singleinstance.MsgActivate:
			ui.Show()
			ui.Emit("activateWindow", map[string]bool{"focus": true})
			return singleinstance.RespOK, nil
		case singleinstance.MsgKill:
			log.Println("[БОБР] Получен сигнал завершения от другого экземпляра. Освобождение ресурсов...")
			go func() {
				time.Sleep(200 * time.Millisecond)
				_ = instance.Release()
				os.Exit(0)
			}()
			return singleinstance.RespOK, nil
		default:
			return "", singleinstance.ErrInvalidMessage
		}
	})

	// Active tunnel state
	var tunnelMu sync.Mutex
	var transitionMu sync.Mutex
	var activeProtocol string
	var activeAdapter string
	var activeProfileID string
	var activeProfileName string
	var activeBypassDomains []string
	var isRunning bool
	var isSwitching bool

	// Stop any running tunnel
	var stopCurrentTunnel func()

	// Initialize System Tray
	var systemTray *tray.Tray
	systemTray, err = tray.New(
		func() {
			// onToggle
			ui.ToggleVisibility()
		},
		func() {
			// onDisconnect
			if stopCurrentTunnel != nil {
				go func() {
					defer crash.Recover("Tray onDisconnect")
					stopCurrentTunnel()
				}()
			}
		},
		func() {
			// onSettings
			ui.Show()
			ui.Emit("openSettings", nil)
		},
		func() {
			// onExit
			if stopCurrentTunnel != nil {
				stopCurrentTunnel()
			}
			if systemTray != nil {
				systemTray.Destroy()
			}
			ui.Close()
			_ = instance.Release()
			os.Exit(0)
		},
	)
	if err != nil {
		log.Printf("[ВНИМАНИЕ] Ошибка создания системного трея: %v", err)
	} else if systemTray != nil {
		defer systemTray.Destroy()
	}

	// Event forwarder to UI (deduplicating stateChange to prevent DOM re-render storm)
	forwardEvent := func(proto string) vpn.EventListener {
		var lastState vpn.State
		var stateMu sync.Mutex
		return func(ev vpn.Event) {
			tag := "БОБР"
			stateChanged := false

			stateMu.Lock()
			if ev.State != lastState {
				lastState = ev.State
				stateChanged = true
			}
			stateMu.Unlock()

			tunnelMu.Lock()
			switching := isSwitching
			curProto := activeProtocol
			curAdapter := activeAdapter
			curProfName := activeProfileName

			if ev.State == vpn.StateConnected {
				tag = "ПЛОТИНА"
				isRunning = true
				if systemTray != nil {
					systemTray.SetStatus(true, curProfName)
				}

				// Apply host routing exceptions for bypass
				bypassToApply := make([]string, len(activeBypassDomains))
				copy(bypassToApply, activeBypassDomains)

				if len(bypassToApply) > 0 {
					go func(exceptions []string) {
						defer crash.Recover("ApplyBypassRoutes")
						ui.Log(fmt.Sprintf("Применение исключений маршрутизации (%d записей)...", len(exceptions)), "МАРШРУТЫ")
						added, err := routeMgr.ApplyBypassRoutes(exceptions)
						if err != nil {
							ui.Log(fmt.Sprintf("Ошибка настройки маршрутов обхода: %v", err), "ПРОТЕЧКА")
						} else {
							ui.Log(fmt.Sprintf("Маршруты обхода активированы: %d адресов направлено через физический шлюз", added), "МАРШРУТЫ")
						}
					}(bypassToApply)
				}
			} else if ev.State == vpn.StateDisconnected || ev.State == vpn.StateError {
				if !switching {
					isRunning = false
					activeBypassDomains = nil
					if systemTray != nil {
						systemTray.SetStatus(false, "")
					}
					routeMgr.ClearBypassRoutes()
				}
				if ev.State == vpn.StateError {
					tag = "ПРОТЕЧКА"
				}
			}
			tunnelMu.Unlock()

			ui.Log(ev.Message, tag)

			// If we are actively switching profiles, do NOT emit the old tunnel's disconnection event to UI
			if switching && (ev.State == vpn.StateDisconnected || ev.State == vpn.StateDisconnecting) {
				return
			}

			if stateChanged {
				ui.Emit("stateChange", map[string]interface{}{
					"status":   strings.ToLower(string(ev.State)),
					"message":  ev.Message,
					"protocol": curProto,
					"adapter":  curAdapter,
				})
			}
		}
	}

	amneziaSup.AddListener(forwardEvent("AmneziaWG"))
	openconnectSup.AddListener(forwardEvent("OpenConnect"))

	// Stop any running tunnel
	stopCurrentTunnel = func() {
		tunnelMu.Lock()
		activeProto := activeProtocol
		wasRunning := isRunning || amneziaSup.IsRunning() || openconnectSup.IsRunning()
		switching := isSwitching
		tunnelMu.Unlock()

		if !wasRunning {
			return
		}

		ui.Log("Остановка гидротурбины...", "БОБР")
		ctx, cancel := context.WithTimeout(context.Background(), 4*time.Second)
		defer cancel()

		if activeProto == "openconnect" {
			_ = openconnectSup.Stop(ctx)
		} else {
			_ = amneziaSup.Stop(ctx)
		}
		// Also ensure both supervisors are completely stopped
		_ = amneziaSup.Stop(ctx)
		_ = openconnectSup.Stop(ctx)

		// Cleanly remove any bypass routes
		if n := routeMgr.ClearBypassRoutes(); n > 0 {
			ui.Log(fmt.Sprintf("Маршруты обхода деактивированы (%d удалено)", n), "МАРШРУТЫ")
		}

		tunnelMu.Lock()
		if !switching {
			isRunning = false
			activeBypassDomains = nil
			if systemTray != nil {
				systemTray.SetStatus(false, "")
			}
		}
		tunnelMu.Unlock()
	}

	// Start tunnel for given profile
	startProfileTunnel := func(p config.Profile) {
		go func() {
			defer crash.Recover(fmt.Sprintf("startProfileTunnel(%s)", p.Name))

			transitionMu.Lock()
			defer transitionMu.Unlock()

			tunnelMu.Lock()
			isSwitching = true
			tunnelMu.Unlock()

			stopCurrentTunnel()

			// Prepare bypass exceptions for this profile
			var bypassList []string
			if len(p.BypassDomains) > 0 {
				bypassList = append(bypassList, p.BypassDomains...)
			}
			// Load from %APPDATA%\BobrDobr\bypass.txt if present
			appData := os.Getenv("APPDATA")
			if appData == "" {
				home, _ := os.UserHomeDir()
				appData = filepath.Join(home, "AppData", "Roaming")
			}
			bypassFile := filepath.Join(appData, "BobrDobr", "bypass.txt")
			if fileEntries, err := vpn.ParseBypassExceptionsFile(bypassFile); err == nil && len(fileEntries) > 0 {
				bypassList = append(bypassList, fileEntries...)
			}

			// Clean existing bypass routes and detect physical gateway before tunnel establishes
			routeMgr.ClearBypassRoutes()
			physGw, err := routeMgr.DetectPhysicalGateway()
			if err == nil {
				ui.Log(fmt.Sprintf("Физический интернет-шлюз определен: %s", physGw), "МАРШРУТЫ")
			}

			tunnelMu.Lock()
			activeAdapter = adapterMgr.NextAdapterName("bobr0")
			activeProtocol = p.Protocol
			activeProfileID = p.ID
			activeProfileName = p.Name
			activeBypassDomains = bypassList
			isSwitching = false
			currentAdapter := activeAdapter
			tunnelMu.Unlock()

			ui.Log(fmt.Sprintf("Запуск гидротурбины для профиля '%s' [%s] через адаптер %s...", p.Name, p.Protocol, currentAdapter), "БОБР")

			ui.Emit("stateChange", map[string]interface{}{
				"status":   "connecting",
				"message":  fmt.Sprintf("Подключение к %s...", p.Server),
				"protocol": p.Protocol,
				"adapter":  currentAdapter,
			})

			ctx := context.Background()
			if p.Protocol == "openconnect" && p.OpenConnect != nil {
				camo := ""
				if p.OpenConnect.Camouflage != "" {
					camo = p.OpenConnect.Camouflage
				}
				cfg := vpn.OpenConnectConfig{
					BinaryPath:       openconnectBin,
					Server:           p.OpenConnect.Server,
					Port:             p.OpenConnect.Port,
					Username:         p.OpenConnect.Username,
					Password:         p.OpenConnect.Password,
					Protocol:         p.OpenConnect.Protocol,
					CamouflageSecret: camo,
					Script:           vpncScript,
					InterfaceName:    currentAdapter,
					PhysicalGateway:  physGw,
				}
				if err := openconnectSup.Start(ctx, cfg); err != nil {
					ui.Log(fmt.Sprintf("Ошибка запуска OpenConnect: %v", err), "ПРОТЕЧКА")
					ui.Emit("stateChange", map[string]interface{}{
						"status":   "error",
						"message":  err.Error(),
						"protocol": p.Protocol,
						"adapter":  currentAdapter,
					})
				}
			} else if p.AmneziaConfig != nil || p.RawConfig != "" {
				confText := ""
				if p.AmneziaConfig != nil && p.AmneziaConfig.ConfigContent != "" {
					confText = p.AmneziaConfig.ConfigContent
				} else if p.RawConfig != "" {
					confText = p.RawConfig
				} else if p.AmneziaConfig != nil {
					confText = buildAmneziaWGConfigText(p.AmneziaConfig)
				}
				cfg := vpn.AmneziaConfig{
					BinaryPath:    amneziaBin,
					ConfigContent: confText,
					InterfaceName: currentAdapter,
					WintunDLLDir:  filepath.Dir(wintunDll),
				}
				if err := amneziaSup.Start(ctx, cfg); err != nil {
					ui.Log(fmt.Sprintf("Ошибка запуска AmneziaWG: %v", err), "ПРОТЕЧКА")
					ui.Emit("stateChange", map[string]interface{}{
						"status":   "error",
						"message":  err.Error(),
						"protocol": p.Protocol,
						"adapter":  currentAdapter,
					})
				}
			} else {
				ui.Log("Некорректная конфигурация профиля", "ПРОТЕЧКА")
				ui.Emit("stateChange", map[string]interface{}{
					"status":   "error",
					"message":  "Некорректная конфигурация профиля",
					"protocol": p.Protocol,
					"adapter":  currentAdapter,
				})
			}
		}()
	}

	// Register GUI handlers
	ui.On("ready", func(payload json.RawMessage) {
		if startMinimized {
			hideIfMinimized()
		}

		settings, _ := store.GetSettings()
		profiles, _ := store.ListProfiles()

		ui.Emit("profilesUpdated", map[string]interface{}{
			"profiles":        profiles,
			"activeProfileId": settings.ActiveProfileID,
		})

		expStr := "Бессрочно"
		if !settings.SubscriptionExpiresAt.IsZero() && settings.SubscriptionExpiresAt.Year() > 1 {
			expStr = settings.SubscriptionExpiresAt.Format("02.01.2006")
		}

		username := settings.SubscriptionUsername
		if username == "" {
			if settings.SubscriptionURL != "" {
				username = "Пользователь"
			} else {
				username = "Не указан"
			}
		}

		server := settings.SubscriptionServer
		if server == "" {
			if settings.SubscriptionURL != "" {
				server = "Подписка"
			} else {
				server = "Не указан"
			}
		}

		lastSyncStr := "Не проводилась"
		if !settings.LastSyncTime.IsZero() && settings.LastSyncTime.Year() > 1 {
			lastSyncStr = settings.LastSyncTime.Format("02.01.2006 15:04")
		}

		subInfo := map[string]interface{}{
			"url":        settings.SubscriptionURL,
			"last_sync":  lastSyncStr,
			"status":     "active",
			"expires_at": expStr,
			"username":   username,
			"server":     server,
		}
		ui.Emit("subscriptionUpdated", map[string]interface{}{
			"subscription": subInfo,
		})
		ui.Emit("settingsLoaded", settings)

		if settings.SubscriptionURL != "" {
			go func(subURL string) {
				defer crash.Recover("Startup silent subscription sync")
				time.Sleep(1500 * time.Millisecond)
				subClient := subscription.NewClient(subscription.WithTimeout(15 * time.Second))
				info, err := subClient.FetchSubscription(context.Background(), subURL)
				if err != nil {
					log.Printf("[БОБР] Фоновая синхронизация подписки: %v", err)
					return
				}

				for _, p := range info.Profiles {
					_ = store.SaveProfile(p)
				}
				st, _ := store.GetSettings()
				st.SubscriptionURL = subURL
				st.SubscriptionToken = info.UserID
				st.SubscriptionUsername = info.Username
				st.SubscriptionServer = info.ServerHost
				st.SubscriptionExpiresAt = info.ExpiresAt
				st.LastSyncTime = time.Now()
				_ = store.SaveSettings(st)

				updatedProfiles, _ := store.ListProfiles()
				ui.Emit("profilesUpdated", map[string]interface{}{
					"profiles":        updatedProfiles,
					"activeProfileId": st.ActiveProfileID,
				})

				silentExp := "Бессрочно"
				if !info.ExpiresAt.IsZero() && info.ExpiresAt.Year() > 1 {
					silentExp = info.ExpiresAt.Format("02.01.2006")
				}
				ui.Emit("subscriptionUpdated", map[string]interface{}{
					"subscription": map[string]interface{}{
						"url":        st.SubscriptionURL,
						"username":   info.Username,
						"server":     info.ServerHost,
						"expires_at": silentExp,
						"last_sync":  time.Now().Format("15:04:05"),
					},
				})
				ui.Log(fmt.Sprintf("Фоновая синхронизация подписки завершена: профилей %d", len(info.Profiles)), "БОБР")
			}(settings.SubscriptionURL)
		}

		if settings.AutoConnect && settings.ActiveProfileID != "" {
			for _, p := range profiles {
				if p.ID == settings.ActiveProfileID {
					go func(prof config.Profile) {
						defer crash.Recover("AutoConnect")
						time.Sleep(800 * time.Millisecond)
						startProfileTunnel(prof)
					}(p)
					break
				}
			}
		}

		if !acquired {
			procs, _ := singleinstance.FindOtherProcesses()
			pid := 0
			mode := "Другой процесс BobrDobr"
			if len(procs) > 0 {
				pid = procs[0].PID
				if procs[0].IsInstalled {
					mode = "Установленная версия"
				} else {
					mode = "Портативная версия"
				}
			}
			ui.Emit("instanceConflict", map[string]interface{}{
				"pid":  pid,
				"mode": mode,
			})
		}
	})

	ui.On("toggleTunnel", func(payload json.RawMessage) {
		tunnelMu.Lock()
		running := isRunning
		tunnelMu.Unlock()

		if running {
			stopCurrentTunnel()
		} else {
			settings, _ := store.GetSettings()
			profiles, _ := store.ListProfiles()
			var targetProfile *config.Profile
			for _, p := range profiles {
				if p.ID == settings.ActiveProfileID {
					targetProfile = &p
					break
				}
			}
			if targetProfile == nil && len(profiles) > 0 {
				targetProfile = &profiles[0]
			}
			if targetProfile != nil {
				startProfileTunnel(*targetProfile)
			} else {
				ui.Log("Нет активного профиля для подключения. Выберите профиль из списка.", "ВНИМАНИЕ")
			}
		}
	})

	ui.On("connectProfile", func(payload json.RawMessage) {
		var req struct {
			ID string `json:"id"`
		}
		if err := json.Unmarshal(payload, &req); err == nil && req.ID != "" {
			tunnelMu.Lock()
			running := isRunning
			currentID := activeProfileID
			tunnelMu.Unlock()

			if running && currentID == req.ID {
				stopCurrentTunnel()
				return
			}

			p, err := store.GetProfile(req.ID)
			if err == nil {
				settings, _ := store.GetSettings()
				settings.ActiveProfileID = req.ID
				_ = store.SaveSettings(settings)
				startProfileTunnel(p)
			}
		}
	})

	ui.On("selectProfile", func(payload json.RawMessage) {
		var req struct {
			ID string `json:"id"`
		}
		if err := json.Unmarshal(payload, &req); err == nil && req.ID != "" {
			settings, _ := store.GetSettings()
			settings.ActiveProfileID = req.ID
			_ = store.SaveSettings(settings)
			profiles, _ := store.ListProfiles()
			ui.Emit("profilesUpdated", map[string]interface{}{
				"profiles":        profiles,
				"activeProfileId": req.ID,
			})
		}
	})

	ui.On("deleteProfile", func(payload json.RawMessage) {
		var req struct {
			ID string `json:"id"`
		}
		if err := json.Unmarshal(payload, &req); err == nil && req.ID != "" {
			_ = store.DeleteProfile(req.ID)
			settings, _ := store.GetSettings()
			profiles, _ := store.ListProfiles()
			ui.Emit("profilesUpdated", map[string]interface{}{
				"profiles":        profiles,
				"activeProfileId": settings.ActiveProfileID,
			})
			ui.Log("Профиль удалён", "БОБР")
		}
	})

	ui.On("checkSubscriptionStatus", func(payload json.RawMessage) {
		var req struct {
			URL string `json:"url"`
		}
		if err := json.Unmarshal(payload, &req); err != nil || strings.TrimSpace(req.URL) == "" {
			ui.Emit("subscriptionStatusResult", map[string]interface{}{
				"success": false,
				"error":   "URL подписки не указан",
			})
			return
		}

		go func() {
			defer crash.Recover("checkSubscriptionStatus")
			ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
			defer cancel()

			ui.Log(fmt.Sprintf("Проверка статуса подписки %s...", req.URL), "БОБР")
			subClient := subscription.NewClient(subscription.WithTimeout(10 * time.Second))
			info, err := subClient.FetchSubscription(ctx, req.URL)
			if err != nil {
				ui.Emit("subscriptionStatusResult", map[string]interface{}{
					"success": false,
					"error":   err.Error(),
				})
				return
			}

			ui.Emit("subscriptionStatusResult", map[string]interface{}{
				"success":       true,
				"profilesCount": len(info.Profiles),
				"server":        info.ServerHost,
				"username":      info.Username,
				"expires_at":    info.ExpiresAt.Format("02.01.2006"),
			})
		}()
	})

	ui.On("syncSubscription", func(payload json.RawMessage) {
		var req struct {
			URL string `json:"url"`
		}
		if err := json.Unmarshal(payload, &req); err == nil && req.URL != "" {
			ui.Log(fmt.Sprintf("Синхронизация подписки с %s...", req.URL), "БОБР")
			subClient := subscription.NewClient()
			info, err := subClient.FetchSubscription(context.Background(), req.URL)
			if err != nil {
				ui.Log(fmt.Sprintf("Ошибка обновления подписки: %v", err), "ПРОТЕЧКА")
				return
			}

			for _, p := range info.Profiles {
				_ = store.SaveProfile(p)
			}
			settings, _ := store.GetSettings()
			settings.SubscriptionURL = req.URL
			settings.SubscriptionToken = info.UserID
			settings.SubscriptionUsername = info.Username
			settings.SubscriptionServer = info.ServerHost
			settings.SubscriptionExpiresAt = info.ExpiresAt
			settings.LastSyncTime = time.Now()
			_ = store.SaveSettings(settings)

			profiles, _ := store.ListProfiles()
			ui.Emit("profilesUpdated", map[string]interface{}{
				"profiles":        profiles,
				"activeProfileId": settings.ActiveProfileID,
			})
			expStr := "Бессрочно"
			if !info.ExpiresAt.IsZero() && info.ExpiresAt.Year() > 1 {
				expStr = info.ExpiresAt.Format("02.01.2006")
			}
			ui.Emit("subscriptionUpdated", map[string]interface{}{
				"subscription": map[string]interface{}{
					"url":        settings.SubscriptionURL,
					"username":   info.Username,
					"server":     info.ServerHost,
					"expires_at": expStr,
					"last_sync":  time.Now().Format("15:04:05"),
				},
			})
			ui.Log(fmt.Sprintf("Подписка обновлена: загружено %d профилей", len(info.Profiles)), "ПЛОТИНА")
		}
	})


	ui.On("deleteSubscription", func(payload json.RawMessage) {
		ui.Log("Удаление подписки и связанных подключений...", "БОБР")
		profiles, _ := store.ListProfiles()
		for _, p := range profiles {
			if p.IsSubscription || p.SubID != "" || strings.HasSuffix(strings.ToLower(p.Name), "-sub") {
				_ = store.DeleteProfile(p.ID)
			}
		}
		settings, _ := store.GetSettings()
		settings.SubscriptionURL = ""
		settings.SubscriptionToken = ""
		settings.SubscriptionUsername = ""
		settings.SubscriptionServer = ""
		settings.SubscriptionExpiresAt = time.Time{}
		_ = store.SaveSettings(settings)

		updatedProfiles, _ := store.ListProfiles()
		ui.Emit("profilesUpdated", map[string]interface{}{
			"profiles":        updatedProfiles,
			"activeProfileId": settings.ActiveProfileID,
		})
		ui.Emit("subscriptionUpdated", map[string]interface{}{
			"subscription": map[string]interface{}{
				"url":        "",
				"username":   "Не указан",
				"server":     "Не указан",
				"expires_at": "Бессрочно",
				"last_sync":  "Не проводилась",
			},
		})
		ui.Log("Подписка удалена. Ручные подключения сохранены.", "БОБР")
	})

	ui.On("saveProfile", func(payload json.RawMessage) {
		var p config.Profile
		if err := json.Unmarshal(payload, &p); err == nil {
			if p.ID == "" {
				p.ID = fmt.Sprintf("prof-%d", time.Now().UnixNano())
			}
			if p.Protocol == "amneziawg" && p.AmneziaConfig != nil && p.AmneziaConfig.ConfigContent != "" {
				if parsedCfg, sHost, sPort, err := subscription.ParseAmneziaWGConfigText(p.AmneziaConfig.ConfigContent); err == nil {
					p.AmneziaConfig.Address = parsedCfg.Address
					p.AmneziaConfig.DNS = parsedCfg.DNS
					p.AmneziaConfig.PrivateKey = parsedCfg.PrivateKey
					p.AmneziaConfig.PublicKey = parsedCfg.PublicKey
					p.AmneziaConfig.PresharedKey = parsedCfg.PresharedKey
					p.AmneziaConfig.Endpoint = parsedCfg.Endpoint
					p.AmneziaConfig.AllowedIPs = parsedCfg.AllowedIPs
					p.AmneziaConfig.Jc = parsedCfg.Jc
					p.AmneziaConfig.Jmin = parsedCfg.Jmin
					p.AmneziaConfig.Jmax = parsedCfg.Jmax
					p.AmneziaConfig.S1 = parsedCfg.S1
					p.AmneziaConfig.S2 = parsedCfg.S2
					p.AmneziaConfig.H1 = parsedCfg.H1
					p.AmneziaConfig.H2 = parsedCfg.H2
					p.AmneziaConfig.H3 = parsedCfg.H3
					p.AmneziaConfig.H4 = parsedCfg.H4
					if p.Server == "" || p.Server == "custom" {
						p.Server = sHost
					}
					if p.Port == 0 || p.Port == 443 {
						p.Port = sPort
					}
					p.Address = parsedCfg.Address
				}
				p.RawConfig = p.AmneziaConfig.ConfigContent
			}
			_ = store.SaveProfile(p)
			updatedProfiles, _ := store.ListProfiles()
			settings, _ := store.GetSettings()
			ui.Emit("profilesUpdated", map[string]interface{}{
				"profiles":        updatedProfiles,
				"activeProfileId": settings.ActiveProfileID,
			})
			ui.Log(fmt.Sprintf("Профиль '%s' сохранён", p.Name), "БОБР")
		}
	})

	ui.On("getProfile", func(payload json.RawMessage) {
		var req struct {
			ID string `json:"id"`
		}
		if err := json.Unmarshal(payload, &req); err == nil && req.ID != "" {
			if p, err := store.GetProfile(req.ID); err == nil {
				ui.Emit("profileDetails", p)
			}
		}
	})

	ui.On("parseConf", func(payload json.RawMessage) {
		var req struct {
			Content string `json:"content"`
		}
		if err := json.Unmarshal(payload, &req); err == nil && req.Content != "" {
			if cfg, host, port, err := subscription.ParseAmneziaWGConfigText(req.Content); err == nil {
				ui.Emit("confParsed", map[string]interface{}{
					"valid":    true,
					"host":     host,
					"port":     port,
					"address":  cfg.Address,
					"dns":      cfg.DNS,
					"endpoint": cfg.Endpoint,
					"jc":       cfg.Jc,
					"jmin":     cfg.Jmin,
					"jmax":     cfg.Jmax,
					"s1":       cfg.S1,
					"s2":       cfg.S2,
					"h1":       cfg.H1,
					"h2":       cfg.H2,
					"h3":       cfg.H3,
					"h4":       cfg.H4,
				})
			} else {
				ui.Emit("confParsed", map[string]interface{}{
					"valid": false,
					"error": err.Error(),
				})
			}
		}
	})

	ui.On("openCabinet", func(payload json.RawMessage) {
		var req struct {
			URL string `json:"url"`
		}
		_ = json.Unmarshal(payload, &req)

		targetURL := req.URL
		if targetURL == "" {
			settings, _ := store.GetSettings()
			targetURL = "https://persona.netphoenix.ru"
			if settings.SubscriptionURL != "" {
				targetURL = subscription.ExtractCabinetURL(nil, settings.SubscriptionURL)
			}
		}
		ui.Log(fmt.Sprintf("Открытие ссылки в браузере: %s", targetURL), "БОБР")
		if runtime.GOOS == "windows" {
			_ = exec.Command("rundll32", "url.dll,FileProtocolHandler", targetURL).Start()
		}
	})

	ui.On("instanceAction", func(payload json.RawMessage) {
		var req struct {
			Action string `json:"action"`
		}
		_ = json.Unmarshal(payload, &req)
		if req.Action == "kill_other" {
			ui.Log("Завершение конфликтующих процессов BobrDobr...", "БОБР")
			_ = singleinstance.TerminateOtherBobrDobrProcesses()
			time.Sleep(500 * time.Millisecond)
			_, _ = instance.TryAcquire()
		}
	})

	ui.On("minimize", func(payload json.RawMessage) {
		ui.Hide()
	})

	ui.On("hideToTray", func(payload json.RawMessage) {
		ui.Hide()
	})

	ui.On("showWindow", func(payload json.RawMessage) {
		ui.Show()
	})

	// Intercept native Windows (X) close button on title bar
	ui.SetOnClose(func() bool {
		settings, _ := store.GetSettings()
		if settings.CloseAction == "exit" {
			stopCurrentTunnel()
			if systemTray != nil {
				systemTray.Destroy()
			}
			_ = instance.Release()
			return false // allow window to close and app to terminate
		}
		// Default: hide to system tray, keeping VPN connection active
		return true // intercepted, hide to tray
	})

	ui.On("close", func(payload json.RawMessage) {
		settings, _ := store.GetSettings()
		if settings.CloseAction == "exit" {
			stopCurrentTunnel()
			if systemTray != nil {
				systemTray.Destroy()
			}
			ui.Close()
			_ = instance.Release()
			os.Exit(0)
		} else {
			ui.Hide()
		}
	})

	ui.On("quitApp", func(payload json.RawMessage) {
		stopCurrentTunnel()
		if systemTray != nil {
			systemTray.Destroy()
		}
		ui.Close()
		_ = instance.Release()
		os.Exit(0)
	})

	ui.On("copyToClipboard", func(payload json.RawMessage) {
		var req struct {
			Text string `json:"text"`
		}
		if err := json.Unmarshal(payload, &req); err == nil && req.Text != "" {
			_ = gui.SetClipboardText(req.Text)
		}
	})

	ui.On("getSettings", func(payload json.RawMessage) {
		settings, _ := store.GetSettings()
		ui.Emit("settingsLoaded", settings)
	})

	ui.On("saveSettings", func(payload json.RawMessage) {
		var newSettings config.Settings
		if err := json.Unmarshal(payload, &newSettings); err == nil {
			cur, _ := store.GetSettings()
			cur.AutoStart = newSettings.AutoStart
			cur.CloseAction = newSettings.CloseAction
			cur.AutoConnect = newSettings.AutoConnect
			cur.Notifications = newSettings.Notifications
			cur.CheckUpdates = newSettings.CheckUpdates
			_ = store.SaveSettings(cur)
			_ = gui.SetAutoStart(cur.AutoStart)
			ui.Log("Настройки программы успешно обновлены", "БОБР")
			ui.Emit("settingsLoaded", cur)
		}
	})

	ui.On("openAppDataDir", func(payload json.RawMessage) {
		if runtime.GOOS == "windows" {
			_ = exec.Command("explorer.exe", appDir).Start()
		}
	})

	ui.On("openLogDir", func(payload json.RawMessage) {
		if runtime.GOOS == "windows" {
			logDir := filepath.Join(appDir, "log")
			_ = exec.Command("explorer.exe", logDir).Start()
		}
	})

	ui.On("getBypassExceptions", func(payload json.RawMessage) {
		appData := os.Getenv("APPDATA")
		if appData == "" {
			home, _ := os.UserHomeDir()
			appData = filepath.Join(home, "AppData", "Roaming")
		}
		bypassFile := filepath.Join(appData, "BobrDobr", "bypass.txt")
		entries, _ := vpn.ParseBypassExceptionsFile(bypassFile)
		active := routeMgr.GetActiveRoutes()
		ui.Emit("bypassExceptionsLoaded", map[string]interface{}{
			"fileEntries":  entries,
			"activeRoutes": active,
			"gateway":      routeMgr.CachedGateway(),
		})
	})

	ui.On("saveBypassExceptions", func(payload json.RawMessage) {
		var req struct {
			Content string   `json:"content"`
			Entries []string `json:"entries"`
		}
		if err := json.Unmarshal(payload, &req); err == nil {
			appData := os.Getenv("APPDATA")
			if appData == "" {
				home, _ := os.UserHomeDir()
				appData = filepath.Join(home, "AppData", "Roaming")
			}
			bypassDir := filepath.Join(appData, "BobrDobr")
			_ = os.MkdirAll(bypassDir, 0755)
			bypassFile := filepath.Join(bypassDir, "bypass.txt")

			textToSave := req.Content
			if textToSave == "" && len(req.Entries) > 0 {
				textToSave = strings.Join(req.Entries, "\r\n") + "\r\n"
			}
			_ = os.WriteFile(bypassFile, []byte(textToSave), 0644)
			ui.Log("Файл исключений обхода сохранен: %APPDATA%\\BobrDobr\\bypass.txt", "МАРШРУТЫ")
		}
	})

	currentAppVersion := "1.2.2"

	ui.On("checkUpdate", func(payload json.RawMessage) {
		ui.Log("Проверка обновлений на сервере...", "БОБР")
		go func() {
			defer crash.Recover("checkUpdate")
			ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
			defer cancel()
			rel, hasUpdate, err := updater.CheckUpdate(ctx, "", currentAppVersion)
			if err != nil {
				ui.Log(fmt.Sprintf("Ошибка проверки обновлений: %v", err), "ПРОТЕЧКА")
				ui.Emit("updateCheckResult", map[string]interface{}{
					"has_update": false,
					"error":      err.Error(),
				})
				return
			}
			if hasUpdate && rel != nil {
				ui.Log(fmt.Sprintf("Доступно обновление: %s (%s)", rel.Version, rel.Title), "ПЛОТИНА")
				ui.Emit("updateAvailable", rel)
			} else {
				ui.Log(fmt.Sprintf("Установлена актуальная версия BobrDobr VPN (v%s)", currentAppVersion), "БОБР")
				ui.Emit("updateCheckResult", map[string]interface{}{
					"has_update": false,
					"latest":     currentAppVersion,
				})
			}
		}()
	})

	ui.On("downloadUpdate", func(payload json.RawMessage) {
		var req struct {
			URL string `json:"url"`
		}
		_ = json.Unmarshal(payload, &req)
		ui.Log("Загрузка пакета обновления...", "БОБР")

		go func() {
			defer crash.Recover("downloadUpdate")
			ctx := context.Background()
			dlURL := req.URL
			if dlURL == "" {
				rel, _, err := updater.CheckUpdate(ctx, "", currentAppVersion)
				if err == nil && rel != nil {
					dlURL = rel.DownloadURL
				}
			}
			if dlURL == "" {
				ui.Log("Не найден URL для скачивания обновления", "ПРОТЕЧКА")
				ui.Emit("downloadError", map[string]string{"error": "Не найден URL для скачивания обновления"})
				return
			}

			ui.Emit("downloadProgress", map[string]int{"percent": 0})
			installerPath, err := updater.DownloadInstaller(ctx, dlURL, func(percent int) {
				ui.Emit("downloadProgress", map[string]int{"percent": percent})
			})
			if err != nil {
				ui.Log(fmt.Sprintf("Ошибка загрузки обновления: %v", err), "ПРОТЕЧКА")
				ui.Emit("downloadError", map[string]string{"error": err.Error()})
				return
			}

			ui.Log(fmt.Sprintf("Обновление загружено: %s. Запуск установщика...", installerPath), "ПЛОТИНА")
			time.Sleep(500 * time.Millisecond)

			stopCurrentTunnel()
			if systemTray != nil {
				systemTray.Destroy()
			}
			_ = instance.Release()

			if err := updater.LaunchInstallerAndExit(installerPath, false); err != nil {
				ui.Log(fmt.Sprintf("Ошибка запуска установщика: %v", err), "ПРОТЕЧКА")
				ui.Emit("downloadError", map[string]string{"error": err.Error()})
				return
			}
			ui.Close()
			os.Exit(0)
		}()
	})

	// Background silent check for updates on startup
	go func() {
		defer crash.Recover("Startup checkUpdate")
		time.Sleep(3500 * time.Millisecond)
		if s, err := store.GetSettings(); err == nil && !s.CheckUpdates {
			return
		}
		ctx, cancel := context.WithTimeout(context.Background(), 12*time.Second)
		defer cancel()
		rel, hasUpdate, err := updater.CheckUpdate(ctx, "", currentAppVersion)
		if err == nil && hasUpdate && rel != nil {
			ui.Log(fmt.Sprintf("Обнаружено обновление v%s", rel.Version), "ПЛОТИНА")
			ui.Emit("updateAvailable", rel)
		}
	}()

	// Run GUI loop
	if err := ui.Run(); err != nil {
		log.Printf("[ОШИБКА] Сбой GUI: %v", err)
	}
}
