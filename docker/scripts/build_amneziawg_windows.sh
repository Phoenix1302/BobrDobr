#!/bin/sh
set -e

echo "=== Building AmneziaWG Windows Tunnel Service CLI ==="

WORK_DIR="/tmp/amneziawg-windows"
rm -rf "$WORK_DIR"
git clone https://github.com/amnezia-vpn/amneziawg-windows.git "$WORK_DIR"
cd "$WORK_DIR"

export GOTOOLCHAIN=auto

# Copy full production tunnel components (defaultroutemonitor with socket binding, SetDNS)
cp tunnel/defaultroutemonitor.go .
sed -i 's/package tunnel/package main/' defaultroutemonitor.go

cp tunnel/interfacewatcher.go .
sed -i 's/package tunnel/package main/' interfacewatcher.go

cp tunnel/addressconfig.go .
sed -i 's/package tunnel/package main/' addressconfig.go

# Patch addressconfig.go:
# Keep firewall import and doNotRestrict used, but bypass WFP rule installation
sed -i 's/return firewall.EnableFirewall(tun.LUID(), doNotRestrict, conf.Interface.DNS)/_ = doNotRestrict; _ = firewall.EnableFirewall; log.Println("Bypassing WFP firewall in user mode"); return nil/g' addressconfig.go

# Patch service.go:
# NOTE: In Go source, each error block is TWO lines:
#   serviceError = services.ErrorXxx
#   return
# We replace the serviceError line and delete the following 'return' line.

# 1. Ensure log.SetOutput(os.Stderr) is called
sed -i 's/err = ringlogger.InitGlobalLogger("TUN")/err = ringlogger.InitGlobalLogger("TUN"); log.SetOutput(os.Stderr)/g' service.go

# 2. Don't abort if ringlogger fails (replace assignment, delete next 'return')
sed -i '/serviceError = services.ErrorRingloggerOpen/{
s/.*/\t\tlog.Printf("Ringlogger notice: %v", err); err = nil/
n
/return/d
}' service.go

# 3. Graceful privilege drop (replace assignment, delete next 'return')
sed -i '/serviceError = services.ErrorDropPrivileges/{
s/.*/\t\tlog.Printf("DropPrivileges notice: %v", err); err = nil/
n
/return/d
}' service.go

# 4. Graceful UAPI named pipe (replace assignment, delete next 'return')
sed -i '/serviceError = services.ErrorUAPIListen/{
s/.*/\t\tlog.Printf("UAPI listener notice: %v [skipping named pipe in user mode]", err); err = nil; uapi = nil/
n
/return/d
}' service.go

# 5. Conditionally start UAPI accept loop only if uapi != nil
sed -i 's/log.Println("Listening for UAPI requests")/if uapi != nil { log.Println("Listening for UAPI requests")/g' service.go
sed -i '/err = runScriptCommand(config.Interface.PostUp, config.Name)/i\
\t} \/\/ end if uapi != nil' service.go


# Create our standalone CLI runner main.go
cat > main.go << 'EOF'
package main

import (
	"flag"
	"fmt"
	"io/ioutil"
	"log"
	"os"
	"os/signal"
	"path/filepath"
	"strings"
	"syscall"

	"github.com/amnezia-vpn/amneziawg-windows/v3/conf"
	"golang.org/x/sys/windows/svc"
)

func main() {
	log.SetOutput(os.Stderr)
	log.SetFlags(log.Ldate | log.Ltime | log.Lmicroseconds)

	configPath := flag.String("config", "", "Path to AmneziaWG .conf configuration file")
	name := flag.String("name", "", "Tunnel adapter name")
	flag.Parse()

	targetConfig := *configPath
	if targetConfig == "" && flag.NArg() > 0 {
		targetConfig = flag.Arg(0)
	}

	if targetConfig == "" {
		fmt.Fprintf(os.Stderr, "Usage: amneziawg-go.exe -config path/to/awg.conf [-name adapter_name]\n")
		os.Exit(1)
	}

	// Use system temp directory for cached configurations and logs
	conf.PresetRootDirectory(os.TempDir())

	confBytes, err := ioutil.ReadFile(targetConfig)
	if err != nil {
		log.Fatalf("Failed to read configuration file: %v", err)
	}

	tunnelName := *name
	if tunnelName == "" {
		base := filepath.Base(targetConfig)
		ext := filepath.Ext(base)
		tunnelName = strings.TrimSuffix(base, ext)
		if tunnelName == "" {
			tunnelName = "awg0"
		}
	}

	log.Printf("[AmneziaWG] Initializing tunnel [%s] from %s", tunnelName, targetConfig)

	r := make(chan svc.ChangeRequest)
	changes := make(chan svc.Status, 10)

	term := make(chan os.Signal, 2)
	signal.Notify(term, os.Interrupt, os.Kill, syscall.SIGTERM)

	service := &tunnelService{
		ConfString: string(confBytes),
		TunnelName: tunnelName,
	}

	go func() {
		sig := <-term
		log.Printf("[AmneziaWG] Received signal %v, terminating tunnel...", sig)
		r <- svc.ChangeRequest{Cmd: svc.Stop}
	}()

	go func() {
		for st := range changes {
			switch st.State {
			case svc.Running:
				log.Println("[AmneziaWG] Device started")
				log.Println("[AmneziaWG] Startup complete")
			case svc.Stopped:
				log.Println("[AmneziaWG] Tunnel stopped")
			}
		}
	}()

	svcSpecificEC, exitCode := service.Execute(nil, r, changes)
	if exitCode != 0 {
		log.Fatalf("[AmneziaWG] Tunnel exited with error: svcSpecific=%v code=%d", svcSpecificEC, exitCode)
	}
	log.Println("[AmneziaWG] Tunnel terminated cleanly.")
}
EOF

echo "[*] Compiling amneziawg-go.exe for Windows x64..."
GOOS=windows GOARCH=amd64 CGO_ENABLED=0 go build -ldflags="-s -w" -v -o /workspace/bin/windows/amneziawg-go.exe

cp /workspace/bin/windows/amneziawg-go.exe /workspace/dist/windows/amneziawg-go.exe

echo "[+] amneziawg-go.exe successfully compiled and deployed to bin/ and dist/!"
