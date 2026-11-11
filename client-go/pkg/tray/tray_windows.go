//go:build windows

package tray

import (
	"fmt"
	"os"
	"path/filepath"
	"runtime"
	"sync"
	"syscall"
	"unsafe"

	"golang.org/x/sys/windows"
)

var (
	modshell32            = windows.NewLazySystemDLL("shell32.dll")
	moduser32             = windows.NewLazySystemDLL("user32.dll")
	modkernel32           = windows.NewLazySystemDLL("kernel32.dll")
	moduxtheme            = windows.NewLazySystemDLL("uxtheme.dll")

	procShell_NotifyIconW = modshell32.NewProc("Shell_NotifyIconW")
	procDefWindowProcW    = moduser32.NewProc("DefWindowProcW")
	procRegisterClassExW  = moduser32.NewProc("RegisterClassExW")
	procCreateWindowExW   = moduser32.NewProc("CreateWindowExW")
	procDestroyWindow     = moduser32.NewProc("DestroyWindow")
	procGetMessageW       = moduser32.NewProc("GetMessageW")
	procTranslateMessage  = moduser32.NewProc("TranslateMessage")
	procDispatchMessageW  = moduser32.NewProc("DispatchMessageW")
	procPostQuitMessage   = moduser32.NewProc("PostQuitMessage")
	procPostMessageW      = moduser32.NewProc("PostMessageW")
	procLoadImageW        = moduser32.NewProc("LoadImageW")
	procLoadIconW         = moduser32.NewProc("LoadIconW")
	procCreatePopupMenu   = moduser32.NewProc("CreatePopupMenu")
	procDestroyMenu       = moduser32.NewProc("DestroyMenu")
	procAppendMenuW       = moduser32.NewProc("AppendMenuW")
	procTrackPopupMenuEx  = moduser32.NewProc("TrackPopupMenuEx")
	procGetCursorPos      = moduser32.NewProc("GetCursorPos")
	procSetForegroundWindow = moduser32.NewProc("SetForegroundWindow")
	procGetModuleHandleW    = modkernel32.NewProc("GetModuleHandleW")
	procGetProcAddress      = modkernel32.NewProc("GetProcAddress")
)

// initUxThemeDarkMode enables native Windows 10/11 Dark Mode for Win32 popup menus via uxtheme ordinals
func initUxThemeDarkMode(hwnd uintptr) {
	hUxTheme, err := windows.LoadLibrary("uxtheme.dll")
	if err != nil || hUxTheme == 0 {
		return
	}
	// Ordinal 135: SetPreferredAppMode(2) - 2 = ForceDark
	proc135, _, _ := procGetProcAddress.Call(uintptr(hUxTheme), 135)
	if proc135 != 0 {
		_, _, _ = syscall.SyscallN(proc135, 2)
	}
	// Ordinal 133: AllowDarkModeForWindow(hwnd, 1)
	if hwnd != 0 {
		proc133, _, _ := procGetProcAddress.Call(uintptr(hUxTheme), 133)
		if proc133 != 0 {
			_, _, _ = syscall.SyscallN(proc133, hwnd, 1)
		}
	}
}

const (
	NIM_ADD        = 0x00000000
	NIM_MODIFY     = 0x00000001
	NIM_DELETE     = 0x00000002
	NIM_SETVERSION = 0x00000004

	NIF_MESSAGE = 0x00000001
	NIF_ICON    = 0x00000002
	NIF_TIP     = 0x00000004
	NIF_INFO    = 0x00000010

	NIIF_NONE = 0x00000000
	NIIF_INFO = 0x00000001

	WM_NULL         = 0x0000
	WM_USER         = 0x0400
	WM_TRAYICON     = WM_USER + 101
	WM_COMMAND      = 0x0111
	WM_LBUTTONUP    = 0x0202
	WM_LBUTTONDBLCLK = 0x0203
	WM_RBUTTONUP    = 0x0205

	NIN_BALLOONUSERCLICK = 0x0405

	IMAGE_ICON     = 1
	LR_LOADFROMFILE = 0x00000010
	LR_DEFAULTSIZE = 0x00000040

	MF_STRING    = 0x00000000
	MF_GRAYED    = 0x00000001
	MF_DISABLED  = 0x00000002
	MF_SEPARATOR = 0x00000800

	TPM_RETURNCMD   = 0x0100
	TPM_RIGHTBUTTON = 0x0002

	ID_MENU_HEADER     = 1001
	ID_MENU_TOGGLE     = 1002
	ID_MENU_STATUS     = 1003
	ID_MENU_DISCONNECT = 1004
	ID_MENU_EXIT       = 1005
	ID_MENU_SETTINGS   = 1006
)

type NOTIFYICONDATAW struct {
	cbSize           uint32
	hWnd             windows.HWND
	uID              uint32
	uFlags           uint32
	uCallbackMessage uint32
	hIcon            windows.Handle
	szTip            [128]uint16
	dwState          uint32
	dwStateMask      uint32
	szInfo           [256]uint16
	uTimeoutOrVersion uint32
	szInfoTitle      [64]uint16
	dwInfoFlags      uint32
	guidItem         windows.GUID
	hBalloonIcon     windows.Handle
}

type POINT struct {
	X int32
	Y int32
}

type WNDCLASSEXW struct {
	cbSize        uint32
	style         uint32
	lpfnWndProc   uintptr
	cbClsExtra    int32
	cbWndExtra    int32
	hInstance     windows.Handle
	hIcon         windows.Handle
	hCursor       windows.Handle
	hbrBackground windows.Handle
	lpszMenuName  *uint16
	lpszClassName *uint16
	hIconSm       windows.Handle
}

// Tray represents the system tray notification icon
type Tray struct {
	hwnd          windows.HWND
	hIcon         windows.Handle
	nid           NOTIFYICONDATAW
	mu            sync.Mutex
	isConnected   bool
	activeProfile string
	tooltip       string
	onToggle      func()
	onDisconnect  func()
	onSettings    func()
	onExit        func()
	destroyed     bool
}

var activeTray *Tray

// wndProc handles tray message events
func wndProc(hwnd windows.HWND, msg uint32, wParam, lParam uintptr) uintptr {
	if msg == WM_TRAYICON {
		switch lParam {
		case WM_LBUTTONUP, WM_LBUTTONDBLCLK:
			if activeTray != nil && activeTray.onToggle != nil {
				go activeTray.onToggle()
			}
			return 0

		case WM_RBUTTONUP:
			if activeTray != nil {
				activeTray.showContextMenu()
			}
			return 0

		case NIN_BALLOONUSERCLICK:
			if activeTray != nil && activeTray.onToggle != nil {
				go activeTray.onToggle()
			}
			return 0
		}
	}
	r, _, _ := procDefWindowProcW.Call(uintptr(hwnd), uintptr(msg), wParam, lParam)
	return r
}

// New creates and initializes the native Windows system tray icon
func New(onToggle, onDisconnect, onSettings, onExit func()) (*Tray, error) {
	t := &Tray{
		onToggle:     onToggle,
		onDisconnect: onDisconnect,
		onSettings:   onSettings,
		onExit:       onExit,
		tooltip:      "БобрДобр VPN - Готов к работе",
	}

	activeTray = t

	readyCh := make(chan error, 1)

	go func() {
		runtime.LockOSThread()
		defer runtime.UnlockOSThread()

		hInst, _, _ := procGetModuleHandleW.Call(0)

		// Enable Dark Mode for popup menus on Windows 10 (1903+) / Windows 11
		initUxThemeDarkMode(0)

		className, _ := windows.UTF16PtrFromString("BobrDobrTrayClass")
		wcex := WNDCLASSEXW{
			cbSize:        uint32(unsafe.Sizeof(WNDCLASSEXW{})),
			lpfnWndProc:   syscall.NewCallback(wndProc),
			hInstance:     windows.Handle(hInst),
			lpszClassName: className,
		}

		regRet, _, _ := procRegisterClassExW.Call(uintptr(unsafe.Pointer(&wcex)))
		if regRet == 0 {
			// Class might already be registered in process
		}

		wndName, _ := windows.UTF16PtrFromString("BobrDobrTrayWindow")
		hwnd, _, _ := procCreateWindowExW.Call(
			0,
			uintptr(unsafe.Pointer(className)),
			uintptr(unsafe.Pointer(wndName)),
			0, 0, 0, 0, 0,
			0, 0, hInst, 0,
		)

		if hwnd == 0 {
			readyCh <- fmt.Errorf("failed to create tray message window")
			return
		}

		if hwnd != 0 {
			initUxThemeDarkMode(hwnd)
		}

		t.hwnd = windows.HWND(hwnd)

		// 1. Load Icon: first try embedded resource ID 2 (rsrc generated), then ID 1, then fallback to assets
		var hIcon uintptr
		for _, resID := range []uintptr{2, 1} {
			loaded, _, _ := procLoadImageW.Call(
				hInst,
				resID,
				IMAGE_ICON,
				16, 16,
				0x00008000, // LR_SHARED
			)
			if loaded != 0 {
				hIcon = loaded
				break
			}
			loaded, _, _ = procLoadIconW.Call(hInst, resID)
			if loaded != 0 {
				hIcon = loaded
				break
			}
		}

		if hIcon == 0 {
			// Try loading from relative or installed assets folder
			exePath, _ := os.Executable()
			exeDir := filepath.Dir(exePath)
			candidates := []string{
				filepath.Join(exeDir, "assets", "bobr_logo.ico"),
				filepath.Join(exeDir, "bobr_logo.ico"),
				filepath.Join(exeDir, "..", "assets", "bobr_logo.ico"),
				"assets/bobr_logo.ico",
			}
			for _, c := range candidates {
				if _, err := os.Stat(c); err == nil {
					cPtr, _ := windows.UTF16PtrFromString(c)
					loaded, _, _ := procLoadImageW.Call(
						0,
						uintptr(unsafe.Pointer(cPtr)),
						IMAGE_ICON,
						16, 16,
						LR_LOADFROMFILE|LR_DEFAULTSIZE,
					)
					if loaded != 0 {
						hIcon = loaded
						break
					}
				}
			}
		}

		t.hIcon = windows.Handle(hIcon)

		// Setup NOTIFYICONDATAW
		t.nid = NOTIFYICONDATAW{
			cbSize:           uint32(unsafe.Sizeof(NOTIFYICONDATAW{})),
			hWnd:             t.hwnd,
			uID:              1,
			uFlags:           NIF_MESSAGE | NIF_ICON | NIF_TIP,
			uCallbackMessage: WM_TRAYICON,
			hIcon:            t.hIcon,
		}

		tipChars, _ := windows.UTF16FromString(t.tooltip)
		copy(t.nid.szTip[:], tipChars)

		ret, _, _ := procShell_NotifyIconW.Call(NIM_ADD, uintptr(unsafe.Pointer(&t.nid)))
		if ret == 0 {
			readyCh <- fmt.Errorf("Shell_NotifyIconW NIM_ADD failed")
			return
		}

		readyCh <- nil

		// Windows Message Loop
		var msg struct {
			hwnd    windows.HWND
			message uint32
			wParam  uintptr
			lParam  uintptr
			time    uint32
			pt      POINT
		}

		for {
			ret, _, _ := procGetMessageW.Call(uintptr(unsafe.Pointer(&msg)), 0, 0, 0)
			if int32(ret) <= 0 {
				break
			}
			procTranslateMessage.Call(uintptr(unsafe.Pointer(&msg)))
			procDispatchMessageW.Call(uintptr(unsafe.Pointer(&msg)))
		}
	}()

	if err := <-readyCh; err != nil {
		return nil, err
	}

	return t, nil
}

// showContextMenu displays the modern popup menu on right click
func (t *Tray) showContextMenu() {
	t.showModernMenu()
}

// SetStatus updates connection status in tooltip and context menu
func (t *Tray) SetStatus(connected bool, profileName string) {
	t.mu.Lock()
	defer t.mu.Unlock()

	t.isConnected = connected
	t.activeProfile = profileName

	if connected {
		t.tooltip = fmt.Sprintf("БобрДобр VPN - Плотина: %s (Защищено)", profileName)
	} else {
		t.tooltip = "БобрДобр VPN - Речной трафик идёт открыто"
	}

	tipChars, _ := windows.UTF16FromString(t.tooltip)
	copy(t.nid.szTip[:], tipChars)
	t.nid.uFlags = NIF_TIP

	procShell_NotifyIconW.Call(NIM_MODIFY, uintptr(unsafe.Pointer(&t.nid)))
}

// SetTooltip updates tray hover tooltip
func (t *Tray) SetTooltip(tip string) {
	t.mu.Lock()
	defer t.mu.Unlock()

	t.tooltip = tip
	tipChars, _ := windows.UTF16FromString(tip)
	copy(t.nid.szTip[:], tipChars)
	t.nid.uFlags = NIF_TIP

	procShell_NotifyIconW.Call(NIM_MODIFY, uintptr(unsafe.Pointer(&t.nid)))
}

// ShowNotification displays a balloon / system notification from the tray icon
func (t *Tray) ShowNotification(title, message string) {
	t.mu.Lock()
	defer t.mu.Unlock()

	if t.destroyed || t.hwnd == 0 {
		return
	}

	t.nid.uFlags = NIF_INFO | NIF_MESSAGE
	t.nid.uCallbackMessage = WM_TRAYICON
	t.nid.dwInfoFlags = NIIF_INFO

	for i := range t.nid.szInfoTitle {
		t.nid.szInfoTitle[i] = 0
	}
	titleChars, _ := windows.UTF16FromString(title)
	copy(t.nid.szInfoTitle[:], titleChars)

	for i := range t.nid.szInfo {
		t.nid.szInfo[i] = 0
	}
	msgChars, _ := windows.UTF16FromString(message)
	copy(t.nid.szInfo[:], msgChars)

	procShell_NotifyIconW.Call(NIM_MODIFY, uintptr(unsafe.Pointer(&t.nid)))
}

// ShowActionNotification displays an interactive Windows toast notification with an action button,
// or falls back to a standard balloon notification if buttonText is empty or on failure.
func (t *Tray) ShowActionNotification(title, message, buttonText, protocolArg string) {
	if buttonText != "" {
		if err := ShowToastWithAction("BobrDobr.VPN.Client", title, message, buttonText, protocolArg); err == nil {
			return
		}
	}
	t.ShowNotification(title, message)
}

// Destroy cleans up and removes tray icon
func (t *Tray) Destroy() {
	t.mu.Lock()
	if t.destroyed {
		t.mu.Unlock()
		return
	}
	t.destroyed = true
	t.mu.Unlock()

	procShell_NotifyIconW.Call(NIM_DELETE, uintptr(unsafe.Pointer(&t.nid)))
	if t.hwnd != 0 {
		procPostMessageW.Call(uintptr(t.hwnd), procPostQuitMessage.Addr(), 0, 0)
		procDestroyWindow.Call(uintptr(t.hwnd))
	}
}
