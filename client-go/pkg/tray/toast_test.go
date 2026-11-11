package tray

import (
	"strings"
	"testing"
)

func TestXmlEscape(t *testing.T) {
	cases := []struct {
		input    string
		expected string
	}{
		{"Hello World", "Hello World"},
		{"БобрДобр VPN & Tunnel", "БобрДобр VPN &amp; Tunnel"},
		{"<test>", "&lt;test&gt;"},
		{`"quoted" and 'single'`, "&quot;quoted&quot; and &apos;single&apos;"},
		{"<&>\"'", "&lt;&amp;&gt;&quot;&apos;"},
	}

	for _, c := range cases {
		actual := xmlEscape(c.input)
		if actual != c.expected {
			t.Errorf("xmlEscape(%q) = %q; expected %q", c.input, actual, c.expected)
		}
	}
}

func TestBuildToastXml(t *testing.T) {
	// 1. Without icon and without action button
	xmlNoIconNoBtn := buildToastXml("Тест", "Сообщение", "", "", "")
	expected1 := `<toast launch="bobrdobr://action/activate" activationType="protocol"><visual><binding template="ToastGeneric"><text>Тест</text><text>Сообщение</text></binding></visual></toast>`
	if xmlNoIconNoBtn != expected1 {
		t.Errorf("buildToastXml() = %q; want %q", xmlNoIconNoBtn, expected1)
	}

	// 2. With circular emblem icon and action button
	xmlWithIconAndBtn := buildToastXml(
		"🟢 БобрДобр VPN — Защищено",
		"Подключение успешно установлено: Тест [AmneziaWG]",
		"⚙️ Отключить уведомления",
		"bobrdobr://action/disable-notifications",
		`C:\Program Files\BobrDobr\assets\bobr_logo.ico`,
	)
	expected2 := `<toast launch="bobrdobr://action/activate" activationType="protocol"><visual><binding template="ToastGeneric"><text>🟢 БобрДобр VPN — Защищено</text><text>Подключение успешно установлено: Тест [AmneziaWG]</text><image placement="appLogoOverride" hint-crop="circle" src="C:\Program Files\BobrDobr\assets\bobr_logo.ico"/></binding></visual><actions><action content="⚙️ Отключить уведомления" arguments="bobrdobr://action/disable-notifications" activationType="protocol"/></actions></toast>`
	if xmlWithIconAndBtn != expected2 {
		t.Errorf("buildToastXml() = %q; want %q", xmlWithIconAndBtn, expected2)
	}

	// 3. XML special chars escaping in title, message, button and icon path
	xmlSpecialChars := buildToastXml(
		"Title & <Sub>",
		`Message with "quotes" & 'apostrophes'`,
		"⚙️ Settings & <More>",
		"bobrdobr://action?opt=1&val=2",
		`C:\Path & Files\assets\"icon".ico`,
	)
	if !strings.Contains(xmlSpecialChars, "&amp; &lt;Sub&gt;") {
		t.Errorf("Title not properly escaped in: %s", xmlSpecialChars)
	}
	if !strings.Contains(xmlSpecialChars, "&quot;quotes&quot; &amp; &apos;apostrophes&apos;") {
		t.Errorf("Message not properly escaped in: %s", xmlSpecialChars)
	}
	if !strings.Contains(xmlSpecialChars, "src=\"C:\\Path &amp; Files\\assets\\&quot;icon&quot;.ico\"") {
		t.Errorf("Icon path not properly escaped in: %s", xmlSpecialChars)
	}
	if !strings.Contains(xmlSpecialChars, "arguments=\"bobrdobr://action?opt=1&amp;val=2\"") {
		t.Errorf("Protocol args not properly escaped in: %s", xmlSpecialChars)
	}
}

func TestShowToastWithAction(t *testing.T) {
	// Should not panic or error with valid input
	err := ShowToastWithAction(
		"BobrDobr.VPN.Client",
		"🟢 БобрДобр VPN — Защищено",
		"Подключение успешно установлено: Тест [AmneziaWG]",
		"⚙️ Отключить уведомления",
		"bobrdobr://action/disable-notifications",
	)
	if err != nil {
		t.Fatalf("ShowToastWithAction failed: %v", err)
	}

	// Should not panic or error with empty button (balloon / standard mode)
	err = ShowToastWithAction(
		"BobrDobr.VPN.Client",
		"🔴 БобрДобр VPN — Отключено",
		"Туннель отключён: Тест",
		"",
		"",
	)
	if err != nil {
		t.Fatalf("ShowToastWithAction with empty button failed: %v", err)
	}
}
