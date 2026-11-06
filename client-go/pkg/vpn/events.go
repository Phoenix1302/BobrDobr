package vpn

import "time"

// State represents the current VPN connection lifecycle state.
type State string

const (
	StateDisconnected  State = "Disconnected"
	StateConnecting    State = "Connecting"
	StateConnected     State = "Connected"
	StateDisconnecting State = "Disconnecting"
	StateError         State = "Error"
)

// Event is emitted by VPN supervisors on lifecycle and status changes.
type Event struct {
	State     State                  `json:"state"`
	Message   string                 `json:"message"`
	Channel   string                 `json:"channel,omitempty"` // "stdout", "stderr", "sys"
	Timestamp time.Time              `json:"timestamp"`
	Details   map[string]interface{} `json:"details,omitempty"`
}

// EventListener is a callback function that receives structured VPN events.
type EventListener func(event Event)
