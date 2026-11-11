//go:build !windows

package tray

type Tray struct{}

func New(onToggle, onDisconnect, onSettings, onExit func()) (*Tray, error) {
	return &Tray{}, nil
}

func (t *Tray) SetStatus(connected bool, profileName string) {}

func (t *Tray) SetTooltip(tip string) {}

func (t *Tray) ShowNotification(title, message string) {}

func (t *Tray) ShowActionNotification(title, message, buttonText, protocolArg string) {}

func (t *Tray) Destroy() {}
