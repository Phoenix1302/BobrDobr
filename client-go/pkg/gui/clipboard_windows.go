//go:build windows

package gui

import (
	"fmt"
	"unsafe"

	"golang.org/x/sys/windows"
)

var (
	procOpenClipboard    = moduser32.NewProc("OpenClipboard")
	procCloseClipboard   = moduser32.NewProc("CloseClipboard")
	procEmptyClipboard   = moduser32.NewProc("EmptyClipboard")
	procSetClipboardData = moduser32.NewProc("SetClipboardData")
	procGetClipboardData = moduser32.NewProc("GetClipboardData")

	procGlobalAlloc  = modkernel32.NewProc("GlobalAlloc")
	procGlobalLock   = modkernel32.NewProc("GlobalLock")
	procGlobalUnlock = modkernel32.NewProc("GlobalUnlock")
)

const (
	CF_UNICODETEXT = 13
	GMEM_MOVEABLE  = 0x0002
)

// SetClipboardText sets the system clipboard content to the provided text using Win32 API.
func SetClipboardText(text string) error {
	utf16, err := windows.UTF16FromString(text)
	if err != nil {
		return err
	}

	r, _, errOpen := procOpenClipboard.Call(0)
	if r == 0 {
		return fmt.Errorf("failed to open clipboard: %w", errOpen)
	}
	defer procCloseClipboard.Call()

	procEmptyClipboard.Call()

	bytesLen := uintptr(len(utf16) * 2)
	hMem, _, errAlloc := procGlobalAlloc.Call(GMEM_MOVEABLE, bytesLen)
	if hMem == 0 {
		return fmt.Errorf("GlobalAlloc failed: %w", errAlloc)
	}

	ptr, _, errLock := procGlobalLock.Call(hMem)
	if ptr == 0 {
		return fmt.Errorf("GlobalLock failed: %w", errLock)
	}

	dst := unsafe.Slice((*uint16)(unsafe.Pointer(ptr)), len(utf16))
	copy(dst, utf16)

	procGlobalUnlock.Call(hMem)

	r, _, errSet := procSetClipboardData.Call(CF_UNICODETEXT, hMem)
	if r == 0 {
		return fmt.Errorf("SetClipboardData failed: %w", errSet)
	}

	return nil
}

// GetClipboardText reads plain text from Windows clipboard using Win32 API.
func GetClipboardText() string {
	r, _, _ := procOpenClipboard.Call(0)
	if r == 0 {
		return ""
	}
	defer procCloseClipboard.Call()

	hMem, _, _ := procGetClipboardData.Call(CF_UNICODETEXT)
	if hMem == 0 {
		return ""
	}

	ptr, _, _ := procGlobalLock.Call(hMem)
	if ptr == 0 {
		return ""
	}
	defer procGlobalUnlock.Call(hMem)

	return windows.UTF16PtrToString((*uint16)(unsafe.Pointer(ptr)))
}
