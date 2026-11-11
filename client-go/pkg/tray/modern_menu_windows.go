//go:build windows

package tray

import (
	"sync"
	"syscall"
	"time"
	"unsafe"

	"golang.org/x/sys/windows"
)

var (
	modgdi32   = windows.NewLazySystemDLL("gdi32.dll")
	moddwmapi  = windows.NewLazySystemDLL("dwmapi.dll")

	procBeginPaint             = moduser32.NewProc("BeginPaint")
	procEndPaint               = moduser32.NewProc("EndPaint")
	procGetClientRect          = moduser32.NewProc("GetClientRect")
	procFillRect               = moduser32.NewProc("FillRect")
	procDrawTextW              = moduser32.NewProc("DrawTextW")
	procInvalidateRect         = moduser32.NewProc("InvalidateRect")
	procSetWindowRgn           = moduser32.NewProc("SetWindowRgn")
	procTrackMouseEvent        = moduser32.NewProc("TrackMouseEvent")
	procScreenToClient         = moduser32.NewProc("ScreenToClient")
	procClientToScreen         = moduser32.NewProc("ClientToScreen")
	procLoadCursorW            = moduser32.NewProc("LoadCursorW")
	procSetCursor              = moduser32.NewProc("SetCursor")
	procMonitorFromPoint       = moduser32.NewProc("MonitorFromPoint")
	procGetMonitorInfoW        = moduser32.NewProc("GetMonitorInfoW")
	procSystemParametersInfoW  = moduser32.NewProc("SystemParametersInfoW")
	procSetCapture             = moduser32.NewProc("SetCapture")
	procReleaseCapture         = moduser32.NewProc("ReleaseCapture")
	procShowWindow             = moduser32.NewProc("ShowWindow")
	procGetWindow              = moduser32.NewProc("GetWindow")
	procWindowFromPoint        = moduser32.NewProc("WindowFromPoint")
	procGetAncestor            = moduser32.NewProc("GetAncestor")
	procGetClassNameW          = moduser32.NewProc("GetClassNameW")
	procFindWindowW            = moduser32.NewProc("FindWindowW")
	procIsWindowVisible        = moduser32.NewProc("IsWindowVisible")
	procGetWindowRect          = moduser32.NewProc("GetWindowRect")
	procNotifyWinEvent         = moduser32.NewProc("NotifyWinEvent")

	procCreateCompatibleDC     = modgdi32.NewProc("CreateCompatibleDC")
	procCreateCompatibleBitmap = modgdi32.NewProc("CreateCompatibleBitmap")
	procDeleteDC               = modgdi32.NewProc("DeleteDC")
	procDeleteObject           = modgdi32.NewProc("DeleteObject")
	procSelectObject           = modgdi32.NewProc("SelectObject")
	procGetStockObject         = modgdi32.NewProc("GetStockObject")
	procCreateSolidBrush       = modgdi32.NewProc("CreateSolidBrush")
	procCreatePen              = modgdi32.NewProc("CreatePen")
	procCreateFontW            = modgdi32.NewProc("CreateFontW")
	procSetTextColor           = modgdi32.NewProc("SetTextColor")
	procSetBkMode              = modgdi32.NewProc("SetBkMode")
	procBitBlt                 = modgdi32.NewProc("BitBlt")
	procRoundRect              = modgdi32.NewProc("RoundRect")
	procEllipse                = modgdi32.NewProc("Ellipse")
	procCreateRoundRectRgn     = modgdi32.NewProc("CreateRoundRectRgn")
	procMoveToEx               = modgdi32.NewProc("MoveToEx")
	procLineTo                 = modgdi32.NewProc("LineTo")

	procDwmSetWindowAttribute = moddwmapi.NewProc("DwmSetWindowAttribute")
)

const (
	WS_POPUP         = 0x80000000
	WS_EX_TOPMOST    = 0x00000008
	WS_EX_TOOLWINDOW = 0x00000080

	CS_DROPSHADOW = 0x00020000

	WM_PAINT       = 0x000F
	WM_ERASEBKGND  = 0x0014
	WM_SETCURSOR   = 0x0020
	WM_MOUSEMOVE   = 0x0200
	WM_LBUTTONDOWN = 0x0201
	WM_RBUTTONDOWN = 0x0204
	WM_MBUTTONDOWN = 0x0207
	WM_MOUSELEAVE  = 0x02A3
	WM_ACTIVATE    = 0x0006
	WM_KILLFOCUS   = 0x0008
	WM_KEYDOWN     = 0x0100
	WM_KEYUP       = 0x0101
	WM_CANCELMODE  = 0x001F
	WM_DESTROY     = 0x0002

	VK_ESCAPE = 0x1B

	WA_INACTIVE = 0

	SW_SHOW           = 5
	SW_HIDE           = 0
	SW_SHOWNOACTIVATE = 4

	GA_ROOT  = 2
	GW_CHILD = 5

	EVENT_SYSTEM_MENUPOPUPSTART = 0x0006
	EVENT_SYSTEM_MENUPOPUPEND   = 0x0007
	OBJID_CLIENT                = 0xFFFFFFFC

	DT_LEFT       = 0x00000000
	DT_VCENTER    = 0x00000004
	DT_SINGLELINE = 0x00000020

	TRANSPARENT = 1
	SRCCOPY     = 0x00CC0020

	IDC_ARROW = 32512
	IDC_HAND  = 32649

	PS_SOLID   = 0
	NULL_BRUSH = 5

	TME_LEAVE = 0x00000002

	MONITOR_DEFAULTTONEAREST = 2
	SPI_GETWORKAREA          = 0x0030

	DWMWA_USE_IMMERSIVE_DARK_MODE  = 20
	DWMWA_WINDOW_CORNER_PREFERENCE = 33
	DWMWCP_ROUND                   = 2
)

type RECT struct {
	Left   int32
	Top    int32
	Right  int32
	Bottom int32
}

type PAINTSTRUCT struct {
	hdc         uintptr
	fErase      int32
	rcPaint     RECT
	fRestore    int32
	fIncUpdate  int32
	rgbReserved [32]byte
}

type TRACKMOUSEEVENT struct {
	cbSize      uint32
	dwFlags     uint32
	hwndTrack   windows.HWND
	dwHoverTime uint32
}

type MONITORINFO struct {
	cbSize    uint32
	rcMonitor RECT
	rcWork    RECT
	dwFlags   uint32
}

type modernMenuItem struct {
	text      string
	isHeader  bool
	isSep     bool
	disabled  bool
	hasDot    bool
	dotColor  uint32 // RGB
	action    func()
	rect      RECT
}

type modernMenu struct {
	hwnd          windows.HWND
	items         []modernMenuItem
	hoverIndex    int
	width         int32
	height        int32
	tracking      bool
	hOverflow     windows.HWND
	fromOverflow  bool
	stopKeepAlive chan struct{}
	stopOnce      sync.Once
	dismissOnce   sync.Once
}

func (m *modernMenu) stopKeepAliveRoutine() {
	m.stopOnce.Do(func() {
		if m.stopKeepAlive != nil {
			close(m.stopKeepAlive)
		}
	})
}

func dismissOverflowWindow(h windows.HWND) {
	if h == 0 {
		return
	}
	// Dismiss gracefully via standard Win32 cancel & Escape commands.
	// This lets Windows Explorer / XAML island smoothly close the flyout
	// and update the chevron ToggleButton state to IsChecked=false,
	// so subsequent clicks open on the very first try without requiring two clicks!
	procPostMessageW.Call(uintptr(h), WM_CANCELMODE, 0, 0)
	procPostMessageW.Call(uintptr(h), WM_KEYDOWN, VK_ESCAPE, 0)
	procPostMessageW.Call(uintptr(h), WM_KEYUP, VK_ESCAPE, 0xC0000001)

	hChild, _, _ := procGetWindow.Call(uintptr(h), GW_CHILD)
	if hChild != 0 {
		procPostMessageW.Call(hChild, WM_CANCELMODE, 0, 0)
		procPostMessageW.Call(hChild, WM_KEYDOWN, VK_ESCAPE, 0)
		procPostMessageW.Call(hChild, WM_KEYUP, VK_ESCAPE, 0xC0000001)
	}
}

func (m *modernMenu) dismiss(dismissOverflow bool) {
	m.dismissOnce.Do(func() {
		m.stopKeepAliveRoutine()

		if dismissOverflow && m.fromOverflow && m.hOverflow != 0 {
			dismissOverflowWindow(m.hOverflow)
		}

		activeModernMenuMu.Lock()
		if activeModernMenu == m {
			activeModernMenu = nil
		}
		activeModernMenuMu.Unlock()

		if m.hwnd != 0 {
			h := m.hwnd
			m.hwnd = 0
			procReleaseCapture.Call()
			procDestroyWindow.Call(uintptr(h))
		}
	})
}

func detectOverflowWindow(pt POINT) (windows.HWND, bool) {
	overflowClasses := []string{
		"TopLevelWindowForOverflowXamlIsland", // Windows 11 (22H2+)
		"NotifyIconOverflowWindow",            // Windows 10 / earlier Win 11
	}

	// 1. Check window directly under cursor
	ptVal := uintptr(uint32(pt.X)) | (uintptr(uint32(pt.Y)) << 32)
	hPoint, _, _ := procWindowFromPoint.Call(ptVal)
	if hPoint != 0 {
		hRoot, _, _ := procGetAncestor.Call(hPoint, GA_ROOT)
		if hRoot != 0 {
			var buf [256]uint16
			procGetClassNameW.Call(hRoot, uintptr(unsafe.Pointer(&buf[0])), 256)
			clsName := windows.UTF16ToString(buf[:])
			for _, target := range overflowClasses {
				if clsName == target {
					vis, _, _ := procIsWindowVisible.Call(hRoot)
					if vis != 0 {
						return windows.HWND(hRoot), true
					}
				}
			}
		}
	}

	// 2. Fallback: Search top-level windows for visible overflow window containing pt
	for _, target := range overflowClasses {
		clsPtr, _ := windows.UTF16PtrFromString(target)
		h, _, _ := procFindWindowW.Call(uintptr(unsafe.Pointer(clsPtr)), 0)
		if h != 0 {
			vis, _, _ := procIsWindowVisible.Call(h)
			if vis != 0 {
				var rc RECT
				procGetWindowRect.Call(h, uintptr(unsafe.Pointer(&rc)))
				if pt.X >= rc.Left-8 && pt.X <= rc.Right+8 && pt.Y >= rc.Top-8 && pt.Y <= rc.Bottom+8 {
					return windows.HWND(h), true
				}
			}
		}
	}

	return 0, false
}

// CloseActiveModernMenu dismisses any active tray menu
func CloseActiveModernMenu() {
	activeModernMenuMu.Lock()
	if activeModernMenu != nil {
		old := activeModernMenu
		activeModernMenu = nil
		old.dismiss(true)
	}
	activeModernMenuMu.Unlock()
}

var (
	activeModernMenu   *modernMenu
	activeModernMenuMu sync.Mutex
	menuClassOnce      sync.Once
	menuClassName      = "BobrDobrModernTrayMenuClass"
)

func rgb(r, g, b byte) uint32 {
	return uint32(r) | (uint32(g) << 8) | (uint32(b) << 16)
}

func registerModernMenuClass() {
	menuClassOnce.Do(func() {
		hInst, _, _ := procGetModuleHandleW.Call(0)
		hCursor, _, _ := procLoadCursorW.Call(0, uintptr(IDC_ARROW))

		namePtr, _ := windows.UTF16PtrFromString(menuClassName)
		wcex := WNDCLASSEXW{
			cbSize:        uint32(unsafe.Sizeof(WNDCLASSEXW{})),
			style:         CS_DROPSHADOW,
			lpfnWndProc:   syscall.NewCallback(modernMenuWndProc),
			hInstance:     windows.Handle(hInst),
			hCursor:       windows.Handle(hCursor),
			hbrBackground: 0,
			lpszClassName: namePtr,
		}
		procRegisterClassExW.Call(uintptr(unsafe.Pointer(&wcex)))
	})
}

// showModernMenu displays a sleek Windows 11 / Antigravity styled dark popup menu
func (t *Tray) showModernMenu() {
	activeModernMenuMu.Lock()
	if activeModernMenu != nil {
		old := activeModernMenu
		activeModernMenu = nil
		old.dismiss(false)
	}
	activeModernMenuMu.Unlock()

	registerModernMenuClass()

	t.mu.Lock()
	conn := t.isConnected
	t.mu.Unlock()

	// 1. Build menu items
	var items []modernMenuItem

	// Header: connection status
	if conn {
		items = append(items, modernMenuItem{
			text:     "Плотина построена",
			isHeader: true,
			hasDot:   true,
			dotColor: rgb(16, 185, 129), // Emerald
		})
	} else {
		items = append(items, modernMenuItem{
			text:     "Плотина не построена",
			isHeader: true,
			hasDot:   true,
			dotColor: rgb(148, 163, 184), // Slate
		})
	}

	// Toggle main window
	items = append(items, modernMenuItem{
		text: "Показать главное окно",
		action: func() {
			if t.onToggle != nil {
				go t.onToggle()
			}
		},
	})

	// Disconnect VPN (only if connected)
	if conn {
		items = append(items, modernMenuItem{
			text: "Отключить VPN",
			action: func() {
				if t.onDisconnect != nil {
					go t.onDisconnect()
				}
			},
		})
	}

	// Settings
	items = append(items, modernMenuItem{
		text: "Настройки программы...",
		action: func() {
			if t.onSettings != nil {
				go t.onSettings()
			}
		},
	})

	// Exit
	items = append(items, modernMenuItem{
		text: "Выход из программы",
		action: func() {
			if t.onExit != nil {
				go t.onExit()
			}
		},
	})

	// 2. Calculate menu layout geometry
	menuWidth := int32(236)
	paddingY := int32(8)
	paddingX := int32(6)
	itemGap := int32(2)
	curY := paddingY

	for i := range items {
		it := &items[i]
		if it.isHeader {
			it.rect = RECT{
				Left:   paddingX,
				Top:    curY,
				Right:  menuWidth - paddingX,
				Bottom: curY + 28,
			}
			curY += 28 + 4
		} else if it.isSep {
			it.rect = RECT{
				Left:   paddingX + 4,
				Top:    curY,
				Right:  menuWidth - paddingX - 4,
				Bottom: curY + 9,
			}
			curY += 9
		} else {
			it.rect = RECT{
				Left:   paddingX,
				Top:    curY,
				Right:  menuWidth - paddingX,
				Bottom: curY + 32,
			}
			curY += 32 + itemGap
		}
	}
	menuHeight := curY - itemGap + paddingY

	// 3. Compute popup coordinates based on cursor and monitor work area
	var pt POINT
	procGetCursorPos.Call(uintptr(unsafe.Pointer(&pt)))

	var workArea RECT
	procSystemParametersInfoW.Call(SPI_GETWORKAREA, 0, uintptr(unsafe.Pointer(&workArea)), 0)

	// In 64-bit Windows ABI, POINT (8 bytes) is passed by value in RCX as a packed 64-bit integer
	ptVal := uintptr(uint32(pt.X)) | (uintptr(uint32(pt.Y)) << 32)
	hMon, _, _ := procMonitorFromPoint.Call(ptVal, MONITOR_DEFAULTTONEAREST)
	if hMon != 0 {
		var mi MONITORINFO
		mi.cbSize = uint32(unsafe.Sizeof(mi))
		ret, _, _ := procGetMonitorInfoW.Call(hMon, uintptr(unsafe.Pointer(&mi)))
		if ret != 0 && mi.rcWork.Right > mi.rcWork.Left {
			workArea = mi.rcWork
		}
	}

	if workArea.Right <= workArea.Left || workArea.Bottom <= workArea.Top {
		workArea = RECT{Left: 0, Top: 0, Right: 1920, Bottom: 1040}
	}

	// Position above cursor / tray
	posX := pt.X - menuWidth + 20
	if posX+menuWidth > workArea.Right-8 {
		posX = workArea.Right - menuWidth - 8
	}
	if posX < workArea.Left+8 {
		posX = workArea.Left + 8
	}

	posY := pt.Y - menuHeight - 8
	if posY < workArea.Top+8 {
		posY = pt.Y + 8
	}
	if posY+menuHeight > workArea.Bottom-8 {
		posY = workArea.Bottom - menuHeight - 8
	}

	// Detect if opened from Windows Notification Area Overflow window
	hOverflow, fromOverflow := detectOverflowWindow(pt)
	parentHwnd := uintptr(0)
	if fromOverflow && hOverflow != 0 {
		parentHwnd = uintptr(hOverflow)
	}

	// 4. Create Modern Popup Window
	hInst, _, _ := procGetModuleHandleW.Call(0)
	namePtr, _ := windows.UTF16PtrFromString(menuClassName)
	titlePtr, _ := windows.UTF16PtrFromString("BobrDobrTrayMenu")

	hwnd, _, _ := procCreateWindowExW.Call(
		WS_EX_TOPMOST|WS_EX_TOOLWINDOW,
		uintptr(unsafe.Pointer(namePtr)),
		uintptr(unsafe.Pointer(titlePtr)),
		WS_POPUP,
		uintptr(posX), uintptr(posY),
		uintptr(menuWidth), uintptr(menuHeight),
		parentHwnd, 0, hInst, 0,
	)

	if hwnd == 0 {
		return
	}

	m := &modernMenu{
		hwnd:          windows.HWND(hwnd),
		items:         items,
		hoverIndex:    -1,
		width:         menuWidth,
		height:        menuHeight,
		hOverflow:     hOverflow,
		fromOverflow:  fromOverflow,
		stopKeepAlive: make(chan struct{}),
	}

	activeModernMenuMu.Lock()
	activeModernMenu = m
	activeModernMenuMu.Unlock()

	// Keep overflow window open while modern menu is active
	if fromOverflow && hOverflow != 0 {
		go func(h windows.HWND, stopCh <-chan struct{}) {
			ticker := time.NewTicker(25 * time.Millisecond)
			defer ticker.Stop()
			for {
				select {
				case <-stopCh:
					return
				case <-ticker.C:
					vis, _, _ := procIsWindowVisible.Call(uintptr(h))
					if vis == 0 {
						// SW_SHOWNOACTIVATE = 4: keep overflow window visible without stealing focus
						procShowWindow.Call(uintptr(h), 4)
					}
				}
			}
		}(hOverflow, m.stopKeepAlive)
	}

	// Apply rounded corners (SetWindowRgn for Windows 10/11)
	rgn, _, _ := procCreateRoundRectRgn.Call(0, 0, uintptr(menuWidth+1), uintptr(menuHeight+1), 16, 16)
	if rgn != 0 {
		procSetWindowRgn.Call(hwnd, rgn, 1)
	}

	// Windows 11 DWM rounded corners and dark mode attributes
	if procDwmSetWindowAttribute.Find() == nil {
		roundVal := uint32(DWMWCP_ROUND)
		darkVal := uint32(1)
		_, _, _ = procDwmSetWindowAttribute.Call(hwnd, DWMWA_WINDOW_CORNER_PREFERENCE, uintptr(unsafe.Pointer(&roundVal)), 4)
		_, _, _ = procDwmSetWindowAttribute.Call(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, uintptr(unsafe.Pointer(&darkVal)), 4)
	}

	// Notify shell that menu popup is active
	if procNotifyWinEvent.Find() == nil {
		procNotifyWinEvent.Call(EVENT_SYSTEM_MENUPOPUPSTART, hwnd, uintptr(uint32(OBJID_CLIENT)), 0)
	}

	procShowWindow.Call(hwnd, SW_SHOW)
	procSetForegroundWindow.Call(hwnd)
	procSetCapture.Call(hwnd)
}

func modernMenuWndProc(hwnd windows.HWND, msg uint32, wParam, lParam uintptr) uintptr {
	activeModernMenuMu.Lock()
	m := activeModernMenu
	activeModernMenuMu.Unlock()

	if m == nil || m.hwnd != hwnd {
		r, _, _ := procDefWindowProcW.Call(uintptr(hwnd), uintptr(msg), wParam, lParam)
		return r
	}

	switch msg {
	case WM_ERASEBKGND:
		return 1 // Suppress flicker, painted in WM_PAINT

	case WM_PAINT:
		var ps PAINTSTRUCT
		hdc, _, _ := procBeginPaint.Call(uintptr(hwnd), uintptr(unsafe.Pointer(&ps)))
		if hdc != 0 {
			m.paint(hdc)
			procEndPaint.Call(uintptr(hwnd), uintptr(unsafe.Pointer(&ps)))
		}
		return 0

	case WM_SETCURSOR:
		if m.hoverIndex >= 0 && m.hoverIndex < len(m.items) {
			it := m.items[m.hoverIndex]
			if !it.isHeader && !it.isSep && !it.disabled {
				hHand, _, _ := procLoadCursorW.Call(0, uintptr(IDC_HAND))
				if hHand != 0 {
					procSetCursor.Call(hHand)
					return 1
				}
			}
		}

	case WM_MOUSEMOVE:
		ptX := int32(int16(lParam & 0xFFFF))
		ptY := int32(int16((lParam >> 16) & 0xFFFF))

		// Ensure mouse leave tracking
		if !m.tracking {
			var tme TRACKMOUSEEVENT
			tme.cbSize = uint32(unsafe.Sizeof(tme))
			tme.dwFlags = TME_LEAVE
			tme.hwndTrack = hwnd
			procTrackMouseEvent.Call(uintptr(unsafe.Pointer(&tme)))
			m.tracking = true
		}

		newHover := -1
		for i, it := range m.items {
			if !it.isHeader && !it.isSep && !it.disabled {
				if ptX >= it.rect.Left && ptX <= it.rect.Right && ptY >= it.rect.Top && ptY <= it.rect.Bottom {
					newHover = i
					break
				}
			}
		}

		if newHover != m.hoverIndex {
			m.hoverIndex = newHover
			procInvalidateRect.Call(uintptr(hwnd), 0, 0)
		}
		return 0

	case WM_MOUSELEAVE:
		m.tracking = false
		if m.hoverIndex != -1 {
			m.hoverIndex = -1
			procInvalidateRect.Call(uintptr(hwnd), 0, 0)
		}
		return 0

	case WM_LBUTTONDOWN, WM_RBUTTONDOWN, WM_MBUTTONDOWN:
		ptX := int32(int16(lParam & 0xFFFF))
		ptY := int32(int16((lParam >> 16) & 0xFFFF))

		// Check if click was outside menu boundaries
		if ptX < 0 || ptX > m.width || ptY < 0 || ptY > m.height {
			var ptCur POINT
			procGetCursorPos.Call(uintptr(unsafe.Pointer(&ptCur)))
			ptVal := uintptr(uint32(ptCur.X)) | (uintptr(uint32(ptCur.Y)) << 32)
			hClicked, _, _ := procWindowFromPoint.Call(ptVal)

			dismissOver := true
			if m.fromOverflow && m.hOverflow != 0 {
				var rcOver RECT
				procGetWindowRect.Call(uintptr(m.hOverflow), uintptr(unsafe.Pointer(&rcOver)))
				if ptCur.X >= rcOver.Left && ptCur.X <= rcOver.Right && ptCur.Y >= rcOver.Top && ptCur.Y <= rcOver.Bottom {
					dismissOver = false
				}
			}

			// Release capture first so system can route focus/click naturally
			procReleaseCapture.Call()
			if dismissOver && hClicked != 0 && windows.HWND(hClicked) != m.hwnd && windows.HWND(hClicked) != m.hOverflow {
				procSetForegroundWindow.Call(hClicked)
			}

			m.dismiss(dismissOver)
			return 0
		}
		return 0

	case WM_LBUTTONUP:
		ptX := int32(int16(lParam & 0xFFFF))
		ptY := int32(int16((lParam >> 16) & 0xFFFF))

		clickedIdx := -1
		for i, it := range m.items {
			if !it.isHeader && !it.isSep && !it.disabled {
				if ptX >= it.rect.Left && ptX <= it.rect.Right && ptY >= it.rect.Top && ptY <= it.rect.Bottom {
					clickedIdx = i
					break
				}
			}
		}

		m.dismiss(true)

		if clickedIdx >= 0 && clickedIdx < len(m.items) {
			action := m.items[clickedIdx].action
			if action != nil {
				go action()
			}
		}
		return 0

	case WM_ACTIVATE:
		if wParam&0xFFFF == WA_INACTIVE {
			hAct := windows.HWND(lParam)
			if m.fromOverflow && m.hOverflow != 0 && (hAct == m.hOverflow || hAct == m.hwnd) {
				return 0
			}
			m.dismiss(true)
			return 0
		}

	case WM_KILLFOCUS:
		hNewFocus := windows.HWND(wParam)
		if m.fromOverflow && m.hOverflow != 0 && (hNewFocus == m.hOverflow || hNewFocus == m.hwnd) {
			return 0
		}
		m.dismiss(true)
		return 0

	case WM_KEYDOWN:
		if wParam == VK_ESCAPE {
			m.dismiss(true)
			return 0
		}

	case WM_DESTROY:
		m.stopKeepAliveRoutine()
		if procNotifyWinEvent.Find() == nil {
			procNotifyWinEvent.Call(EVENT_SYSTEM_MENUPOPUPEND, uintptr(hwnd), uintptr(uint32(OBJID_CLIENT)), 0)
		}
		activeModernMenuMu.Lock()
		if activeModernMenu != nil && activeModernMenu.hwnd == hwnd {
			activeModernMenu = nil
		}
		activeModernMenuMu.Unlock()
		return 0
	}

	r, _, _ := procDefWindowProcW.Call(uintptr(hwnd), uintptr(msg), wParam, lParam)
	return r
}

func (m *modernMenu) paint(hdc uintptr) {
	memDC, _, _ := procCreateCompatibleDC.Call(hdc)
	if memDC == 0 {
		return
	}
	defer procDeleteDC.Call(memDC)

	memBmp, _, _ := procCreateCompatibleBitmap.Call(hdc, uintptr(m.width), uintptr(m.height))
	if memBmp == 0 {
		return
	}
	defer procDeleteObject.Call(memBmp)

	oldBmp, _, _ := procSelectObject.Call(memDC, memBmp)
	defer procSelectObject.Call(memDC, oldBmp)

	// 1. Sleek solid dark background (#1c1c1e) with matching border pen (no contrasting stroke)
	bgBrush, _, _ := procCreateSolidBrush.Call(uintptr(rgb(28, 28, 30)))
	defer procDeleteObject.Call(bgBrush)

	borderPen, _, _ := procCreatePen.Call(PS_SOLID, 1, uintptr(rgb(28, 28, 30)))
	defer procDeleteObject.Call(borderPen)

	rcClient := RECT{0, 0, m.width, m.height}
	procFillRect.Call(memDC, uintptr(unsafe.Pointer(&rcClient)), bgBrush)

	oldBrush, _, _ := procSelectObject.Call(memDC, bgBrush)
	oldPen, _, _ := procSelectObject.Call(memDC, borderPen)

	// RoundRect fills interior with bgBrush and strokes border with borderPen in one pass
	procRoundRect.Call(memDC, 0, 0, uintptr(m.width), uintptr(m.height), 16, 16)

	procSelectObject.Call(memDC, oldBrush)
	procSelectObject.Call(memDC, oldPen)

	procSetBkMode.Call(memDC, TRANSPARENT)

	// 2. Prepare Segoe UI fonts
	fontName, _ := windows.UTF16PtrFromString("Segoe UI")
	hNormal := int32(-13)
	hHeader := int32(-11)

	hFontNormal, _, _ := procCreateFontW.Call(
		uintptr(hNormal), 0, 0, 0, 400, // 400 = FW_NORMAL, 13px character height (~10pt)
		0, 0, 0, 1, 0, 0, 5, 0, // CLEARTYPE_QUALITY = 5
		uintptr(unsafe.Pointer(fontName)),
	)
	defer procDeleteObject.Call(hFontNormal)

	hFontHeader, _, _ := procCreateFontW.Call(
		uintptr(hHeader), 0, 0, 0, 600, // 600 = FW_SEMIBOLD, 11px
		0, 0, 0, 1, 0, 0, 5, 0,
		uintptr(unsafe.Pointer(fontName)),
	)
	defer procDeleteObject.Call(hFontHeader)

	// 3. Render Menu Items
	sepPen, _, _ := procCreatePen.Call(PS_SOLID, 1, uintptr(rgb(46, 46, 52)))
	defer procDeleteObject.Call(sepPen)

	hoverBrush, _, _ := procCreateSolidBrush.Call(uintptr(rgb(40, 40, 46)))
	defer procDeleteObject.Call(hoverBrush)

	hoverPen, _, _ := procCreatePen.Call(PS_SOLID, 1, uintptr(rgb(40, 40, 46)))
	defer procDeleteObject.Call(hoverPen)

	for i, it := range m.items {
		if it.isHeader {
			// Header item with status dot
			if it.hasDot {
				dotBrush, _, _ := procCreateSolidBrush.Call(uintptr(it.dotColor))
				dotPen, _, _ := procCreatePen.Call(PS_SOLID, 1, uintptr(it.dotColor))
				oldB, _, _ := procSelectObject.Call(memDC, dotBrush)
				oldP, _, _ := procSelectObject.Call(memDC, dotPen)

				dotY := (it.rect.Top + it.rect.Bottom) / 2
				procEllipse.Call(memDC, uintptr(it.rect.Left+10), uintptr(dotY-3), uintptr(it.rect.Left+17), uintptr(dotY+4))

				procSelectObject.Call(memDC, oldB)
				procSelectObject.Call(memDC, oldP)
				procDeleteObject.Call(dotBrush)
				procDeleteObject.Call(dotPen)
			}

			oldF, _, _ := procSelectObject.Call(memDC, hFontHeader)
			procSetTextColor.Call(memDC, uintptr(rgb(148, 163, 184)))

			textPtr, _ := windows.UTF16PtrFromString(it.text)
			textLeft := it.rect.Left + 8
			if it.hasDot {
				textLeft = it.rect.Left + 24
			}
			textRc := RECT{
				Left:   textLeft,
				Top:    it.rect.Top,
				Right:  it.rect.Right - 8,
				Bottom: it.rect.Bottom,
			}
			procDrawTextW.Call(memDC, uintptr(unsafe.Pointer(textPtr)), ^uintptr(0), uintptr(unsafe.Pointer(&textRc)), DT_LEFT|DT_VCENTER|DT_SINGLELINE)
			procSelectObject.Call(memDC, oldF)

		} else if it.isSep {
			// Separator line
			oldP, _, _ := procSelectObject.Call(memDC, sepPen)
			midY := (it.rect.Top + it.rect.Bottom) / 2
			procMoveToEx.Call(memDC, uintptr(it.rect.Left), uintptr(midY), 0)
			procLineTo.Call(memDC, uintptr(it.rect.Right), uintptr(midY))
			procSelectObject.Call(memDC, oldP)

		} else {
			// Normal Interactive Menu Item
			if i == m.hoverIndex {
				// Rounded hover pill
				oldP, _, _ := procSelectObject.Call(memDC, hoverPen)
				oldB, _, _ := procSelectObject.Call(memDC, hoverBrush)
				procRoundRect.Call(memDC, uintptr(it.rect.Left), uintptr(it.rect.Top), uintptr(it.rect.Right), uintptr(it.rect.Bottom), 8, 8)
				procSelectObject.Call(memDC, oldB)
				procSelectObject.Call(memDC, oldP)
			}

			oldF, _, _ := procSelectObject.Call(memDC, hFontNormal)
			if it.disabled {
				procSetTextColor.Call(memDC, uintptr(rgb(100, 100, 110)))
			} else {
				procSetTextColor.Call(memDC, uintptr(rgb(243, 244, 246)))
			}

			textPtr, _ := windows.UTF16PtrFromString(it.text)
			textRc := RECT{
				Left:   it.rect.Left + 12,
				Top:    it.rect.Top,
				Right:  it.rect.Right - 12,
				Bottom: it.rect.Bottom,
			}
			procDrawTextW.Call(memDC, uintptr(unsafe.Pointer(textPtr)), ^uintptr(0), uintptr(unsafe.Pointer(&textRc)), DT_LEFT|DT_VCENTER|DT_SINGLELINE)
			procSelectObject.Call(memDC, oldF)
		}
	}

	// 4. Blit to window DC
	procBitBlt.Call(hdc, 0, 0, uintptr(m.width), uintptr(m.height), memDC, 0, 0, SRCCOPY)
}
