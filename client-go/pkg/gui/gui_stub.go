//go:build !windows

package gui

import (
	"encoding/json"
	"fmt"
)

type BridgeMessage struct {
	Action  string          `json:"action"`
	Payload json.RawMessage `json:"payload"`
}

type GUI struct {
	title  string
	width  int
	height int
}

func NewGUI(title string, width, height int) *GUI {
	return &GUI{
		title:  title,
		width:  width,
		height: height,
	}
}

func (g *GUI) On(action string, handler func(payload json.RawMessage)) {}

func (g *GUI) SetOnClose(handler func() bool) {}

func (g *GUI) Emit(eventName string, data interface{}) {}

func (g *GUI) Log(text string, tag string) {}

func (g *GUI) Run() error {
	return fmt.Errorf("GUI is only supported on Windows")
}

func (g *GUI) Close() {}

func (g *GUI) Show() {}

func (g *GUI) Hide() {}

func (g *GUI) ToggleVisibility() {}

func (g *GUI) IsVisible() bool { return false }
