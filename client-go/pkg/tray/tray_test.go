package tray

import "testing"

func TestTrayInterface(t *testing.T) {
	tray, err := New(nil, nil, nil, nil)
	if err != nil {
		t.Logf("Tray creation returned error (expected in headless environment): %v", err)
		return
	}
	defer tray.Destroy()

	tray.SetStatus(true, "TestProfile")
	tray.SetTooltip("Test Tooltip")
	tray.ShowNotification("Test Title", "Test Message")
	tray.ShowActionNotification("Test Title", "Test Message", "Test Button", "bobrdobr://action/test")
	tray.SetStatus(false, "")
}
