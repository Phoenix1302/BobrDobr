//go:build windows

package config

import (
	"errors"
	"unsafe"

	"golang.org/x/sys/windows"
)

func dpapiProtect(data []byte) ([]byte, error) {
	if len(data) == 0 {
		return nil, errors.New("cannot protect empty data")
	}
	var inBlob windows.DataBlob
	inBlob.Size = uint32(len(data))
	inBlob.Data = &data[0]

	var outBlob windows.DataBlob
	desc, _ := windows.UTF16PtrFromString("BobrDobrProtectedSecret")
	err := windows.CryptProtectData(&inBlob, desc, nil, 0, nil, 0, &outBlob)
	if err != nil {
		return nil, err
	}
	defer windows.LocalFree(windows.Handle(unsafe.Pointer(outBlob.Data)))

	outBytes := make([]byte, outBlob.Size)
	copy(outBytes, unsafe.Slice((*byte)(unsafe.Pointer(outBlob.Data)), outBlob.Size))
	return outBytes, nil
}

func dpapiUnprotect(data []byte) ([]byte, error) {
	if len(data) == 0 {
		return nil, errors.New("cannot unprotect empty data")
	}
	var inBlob windows.DataBlob
	inBlob.Size = uint32(len(data))
	inBlob.Data = &data[0]

	var outBlob windows.DataBlob
	err := windows.CryptUnprotectData(&inBlob, nil, nil, 0, nil, 0, &outBlob)
	if err != nil {
		return nil, err
	}
	defer windows.LocalFree(windows.Handle(unsafe.Pointer(outBlob.Data)))

	outBytes := make([]byte, outBlob.Size)
	copy(outBytes, unsafe.Slice((*byte)(unsafe.Pointer(outBlob.Data)), outBlob.Size))
	return outBytes, nil
}
