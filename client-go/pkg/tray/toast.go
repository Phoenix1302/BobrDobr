package tray

import (
	"fmt"
	"strings"
)

// xmlEscape properly escapes XML special characters (&, <, >, ", ')
func xmlEscape(s string) string {
	var b strings.Builder
	for _, r := range s {
		switch r {
		case '&':
			b.WriteString("&amp;")
		case '<':
			b.WriteString("&lt;")
		case '>':
			b.WriteString("&gt;")
		case '"':
			b.WriteString("&quot;")
		case '\'':
			b.WriteString("&apos;")
		default:
			b.WriteRune(r)
		}
	}
	return b.String()
}

// buildToastXml builds the Toast XML payload with optional icon and action button.
func buildToastXml(title, message, buttonText, protocolArg, iconPath string) string {
	var actionsXml string
	if buttonText != "" {
		actionsXml = fmt.Sprintf(`<actions><action content="%s" arguments="%s" activationType="protocol"/></actions>`,
			xmlEscape(buttonText), xmlEscape(protocolArg))
	}

	var imageXml string
	if iconPath != "" {
		imageXml = fmt.Sprintf(`<image placement="appLogoOverride" hint-crop="circle" src="%s"/>`,
			xmlEscape(iconPath))
	}

	return fmt.Sprintf(`<toast launch="bobrdobr://action/activate" activationType="protocol"><visual><binding template="ToastGeneric"><text>%s</text><text>%s</text>%s</binding></visual>%s</toast>`,
		xmlEscape(title), xmlEscape(message), imageXml, actionsXml)
}
