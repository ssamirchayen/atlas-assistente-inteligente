from __future__ import annotations

VERSION_LABEL = "ATLAS CORE 1.0  •  SPRINT 26  •  PREMIUM UI  •  LIVE INTERFACE"

STATUS_PALETTE: dict[str, tuple[str, str, str]] = {
    "ONLINE": ("#6EE7B7", "#10261F", "#245743"),
    "ESCUTA ATIVA": ("#67E8F9", "#0C2730", "#185666"),
    "OUVINDO": ("#FCD34D", "#2A230D", "#66551B"),
    "EXECUTANDO": ("#93C5FD", "#101F39", "#244D82"),
    "PROCESSANDO": ("#93C5FD", "#101F39", "#244D82"),
    "FALANDO": ("#C4B5FD", "#211939", "#4D3A78"),
    "CONCLUÍDO": ("#6EE7B7", "#10261F", "#245743"),
    "CANCELANDO": ("#FDBA74", "#2F1D11", "#6A3D1F"),
    "CANCELADO": ("#FDBA74", "#2F1D11", "#6A3D1F"),
    "INTERROMPIDO": ("#FDBA74", "#2F1D11", "#6A3D1F"),
    "NÃO ENTENDI": ("#FDBA74", "#2F1D11", "#6A3D1F"),
    "ATENÇÃO": ("#FDBA74", "#2F1D11", "#6A3D1F"),
    "ERRO": ("#FDA4AF", "#32151B", "#77303B"),
    "DEFAULT": ("#CBD5E1", "#17202E", "#334155"),
}

MESSAGE_PALETTE: dict[str, dict[str, str]] = {
    "user": {
        "accent": "#DDE7FF",
        "background": "#2F5FE9",
        "foreground": "#FFFFFF",
    },
    "atlas": {
        "accent": "#78DCE8",
        "background": "#121D2D",
        "foreground": "#E8EEF7",
    },
    "system": {
        "accent": "#FDBA74",
        "background": "#251A13",
        "foreground": "#FDEAD9",
    },
}


def application_stylesheet() -> str:
    """Design system premium do frontend desktop do Atlas."""

    return """
        * {
            font-family: "Segoe UI";
        }

        QMainWindow,
        QWidget#root,
        QWidget#workspace,
        QWidget#conversationColumn {
            background: #080D15;
        }

        QLabel {
            color: #E7EDF6;
            background: transparent;
        }

        QToolTip {
            background: #111A28;
            color: #E7EDF6;
            border: 1px solid #2B3B52;
            padding: 6px 8px;
        }

        QFrame#sidebar {
            background: #070B12;
            background: qlineargradient(
                x1: 0, y1: 0, x2: 0, y2: 1,
                stop: 0 #080D16,
                stop: 0.55 #070B12,
                stop: 1 #060A10
            );
            border: none;
            border-right: 1px solid #172238;
        }

        QLabel#logoBadge {
            background: #345CFF;
            color: #FFFFFF;
            border: 1px solid #5275FF;
            border-radius: 13px;
            font-size: 23px;
            font-weight: 800;
        }

        QLabel#sidebarBrand {
            color: #F8FAFC;
            font-size: 17px;
            font-weight: 800;
            letter-spacing: 2px;
        }

        QLabel#sidebarCaption {
            color: #7389FF;
            font-size: 9px;
            font-weight: 700;
            letter-spacing: 1px;
        }

        QLabel#productCaption {
            color: #56657A;
            font-size: 8px;
            font-weight: 700;
            letter-spacing: 1px;
        }

        QFrame#sidebarDivider {
            color: #182335;
            background: #182335;
            border: none;
            max-height: 1px;
        }

        QLabel#sidebarSection {
            color: #526278;
            font-size: 9px;
            font-weight: 800;
            letter-spacing: 1px;
            margin-top: 7px;
        }

        QFrame#activeArea {
            background: #111A2B;
            border: 1px solid #273A60;
            border-radius: 12px;
        }

        QLabel#activeAreaMark {
            color: #6B8AFF;
            font-size: 9px;
        }

        QLabel#activeAreaText {
            color: #F8FAFC;
            font-size: 11px;
            font-weight: 700;
        }

        QPushButton#sidebarButton,
        QPushButton#sidebarAccentButton {
            min-height: 20px;
            background: transparent;
            color: #8A99AD;
            border: 1px solid transparent;
            border-radius: 10px;
            padding: 9px 12px;
            text-align: left;
            font-size: 10px;
            font-weight: 600;
        }

        QPushButton#sidebarButton:hover {
            background: #0E1622;
            color: #F8FAFC;
            border-color: #1E2B3E;
        }

        QPushButton#sidebarAccentButton {
            background: #101B31;
            color: #95A9FF;
            border-color: #253A69;
        }

        QPushButton#sidebarAccentButton:hover {
            background: #142242;
            color: #C7D2FE;
            border-color: #385496;
        }

        QPushButton#sidebarButton:disabled,
        QPushButton#sidebarAccentButton:disabled {
            color: #3F4B5D;
            background: transparent;
            border-color: transparent;
        }

        QFrame#privacyCard {
            background: #0C1420;
            border: 1px solid #1B2A3E;
            border-radius: 12px;
        }

        QLabel#privacyTitle {
            color: #65D3B0;
            font-size: 9px;
            font-weight: 800;
            letter-spacing: 1px;
        }

        QLabel#privacyText {
            color: #6E7D90;
            font-size: 9px;
        }

        QLabel#versionLabel {
            color: #3E4A5C;
            font-size: 8px;
            letter-spacing: 1px;
        }

        QFrame#topHeader,
        QFrame#insightsRail {
            background: transparent;
            border: none;
        }

        QLabel#pageEyebrow {
            color: #6B8AFF;
            font-size: 9px;
            font-weight: 800;
            letter-spacing: 1.5px;
        }

        QLabel#pageTitle {
            color: #F8FAFC;
            font-size: 28px;
            font-weight: 750;
        }

        QLabel#pageSubtitle {
            color: #748297;
            font-size: 11px;
        }

        QFrame#headerSignal {
            background: #0D1622;
            border: 1px solid #1E2D43;
            border-radius: 11px;
        }

        QLabel#headerSignalCaption {
            color: #58677A;
            font-size: 8px;
            font-weight: 800;
            letter-spacing: 1px;
        }

        QLabel#headerSignalValue {
            color: #CED8E6;
            font-size: 10px;
            font-weight: 650;
        }

        QFrame#userCard {
            background: #0D1622;
            border: 1px solid #1E2D43;
            border-radius: 13px;
        }

        QLabel#userAvatar {
            background: #17244A;
            color: #AFC0FF;
            border: 1px solid #32477A;
            border-radius: 18px;
            font-size: 12px;
            font-weight: 800;
        }

        QLabel#userName {
            color: #D7E0EC;
            font-size: 10px;
            font-weight: 650;
        }

        QFrame#conversationCard {
            background: #0B111B;
            border: 1px solid #1C2A3E;
            border-radius: 18px;
        }

        QFrame#conversationHeader {
            background: qlineargradient(
                x1: 0, y1: 0, x2: 1, y2: 0,
                stop: 0 #101929,
                stop: 0.6 #0E1622,
                stop: 1 #0C1420
            );
            border: none;
            border-bottom: 1px solid #1D2A3D;
            border-top-left-radius: 18px;
            border-top-right-radius: 18px;
        }

        QLabel#assistantAvatar {
            background: #14244A;
            color: #9DB0FF;
            border: 1px solid #304B89;
            border-radius: 17px;
            font-size: 12px;
            font-weight: 800;
        }

        QLabel#conversationTitle,
        QLabel#cardTitle {
            color: #E9EEF6;
            font-size: 12px;
            font-weight: 750;
        }

        QLabel#conversationCaption,
        QLabel#cardCaption {
            color: #617085;
            font-size: 9px;
        }

        QLabel#sessionLabel {
            color: #75E6B5;
            background: #0D251E;
            border: 1px solid #22513F;
            border-radius: 10px;
            padding: 5px 9px;
            font-size: 9px;
            font-weight: 700;
        }

        QTextEdit#chat {
            background: #0A1019;
            color: #E7EDF6;
            border: none;
            border-bottom-left-radius: 16px;
            border-bottom-right-radius: 16px;
            font-size: 13px;
            selection-background-color: #2947A8;
        }

        QScrollBar:vertical {
            background: transparent;
            width: 8px;
            margin: 6px 2px 6px 0;
        }

        QScrollBar::handle:vertical {
            background: #2A3545;
            border-radius: 4px;
            min-height: 34px;
        }

        QScrollBar::handle:vertical:hover {
            background: #3A485B;
        }

        QScrollBar::add-line:vertical,
        QScrollBar::sub-line:vertical {
            height: 0;
        }

        QFrame#commandPanel {
            background: #0D141F;
            border: 1px solid #1D2A3B;
            border-radius: 15px;
        }

        QLabel#activityMark {
            color: #6B8AFF;
            font-size: 8px;
        }

        QLabel#activityText {
            color: #728197;
            font-size: 9px;
            font-weight: 600;
        }

        QLineEdit#commandInput {
            min-height: 24px;
            background: #090F18;
            color: #E8EEF7;
            border: 1px solid #25344A;
            border-radius: 12px;
            padding: 11px 14px;
            font-size: 11px;
        }

        QLineEdit#commandInput:hover {
            border-color: #334A6B;
        }

        QLineEdit#commandInput:focus {
            background: #0A111C;
            border: 1px solid #5B78FF;
        }

        QPushButton {
            min-height: 22px;
            border-radius: 10px;
            padding: 9px 13px;
            font-size: 10px;
            font-weight: 650;
        }

        QPushButton#primaryButton {
            background: #4169F7;
            color: #FFFFFF;
            border: 1px solid #5579FF;
            min-width: 72px;
        }

        QPushButton#primaryButton:hover {
            background: #5278FF;
            border-color: #6A8AFF;
        }

        QPushButton#primaryButton:pressed {
            background: #3458D8;
        }

        QPushButton#secondaryButton,
        QPushButton#quickButton {
            background: #101925;
            color: #B6C1D0;
            border: 1px solid #26364C;
        }

        QPushButton#secondaryButton:hover,
        QPushButton#quickButton:hover {
            background: #152131;
            color: #F4F7FB;
            border-color: #3A506E;
        }

        QPushButton#quickButton {
            text-align: left;
            padding: 9px 11px;
            font-size: 9px;
        }

        QPushButton#cancelButton {
            min-height: 16px;
            background: transparent;
            color: #F99AA6;
            border: 1px solid #60313A;
            padding: 5px 9px;
            font-size: 9px;
        }

        QPushButton#cancelButton:hover {
            background: #2A151A;
            border-color: #8A4551;
        }

        QPushButton:disabled {
            background: #0D131C;
            color: #465265;
            border-color: #1B2533;
        }

        QLabel#commandHint {
            color: #4C5A6D;
            font-size: 8px;
        }

        QFrame#infoCard,
        QFrame#heroMetricCard {
            background: #0D141F;
            border: 1px solid #1D2A3B;
            border-radius: 14px;
        }

        QFrame#heroMetricCard {
            background: qlineargradient(
                x1: 0, y1: 0, x2: 1, y2: 1,
                stop: 0 #111B31,
                stop: 0.5 #0F1728,
                stop: 1 #0C1421
            );
            border-color: #2B416B;
        }

        QLabel#metricCaption {
            color: #536176;
            font-size: 8px;
            font-weight: 800;
            letter-spacing: 1px;
            margin-top: 4px;
        }

        QLabel#metricValue {
            color: #DCE5F0;
            font-size: 12px;
            font-weight: 700;
        }

        QLabel#resourceLabel {
            color: #8390A2;
            font-size: 9px;
            font-weight: 650;
            margin-top: 5px;
        }

        QProgressBar#resourceBar {
            min-height: 5px;
            max-height: 5px;
            background: #182231;
            border: none;
            border-radius: 2px;
        }

        QProgressBar#resourceBar::chunk {
            background: #5878F6;
            border-radius: 2px;
        }

        QLabel#cardBody {
            color: #708096;
            font-size: 9px;
        }

        QLabel#localState {
            color: #76E4B4;
            background: #0E241D;
            border: 1px solid #23513F;
            border-radius: 9px;
            padding: 7px 9px;
            font-size: 9px;
            font-weight: 700;
            margin-top: 4px;
        }

        QLabel#pulseOrb {
            background: #315CF0;
            color: #DDE5FF;
            border: 1px solid #5579FF;
            border-radius: 24px;
            font-size: 18px;
            font-weight: 800;
        }

        QLabel#pulseTitle {
            color: #F0F4FA;
            font-size: 13px;
            font-weight: 750;
        }

        QLabel#pulseText {
            color: #718096;
            font-size: 9px;
        }


        QLabel#orbState {
            color: #AFC0FF;
            background: #111D36;
            border: 1px solid #2C4270;
            border-radius: 9px;
            padding: 5px 8px;
            font-size: 8px;
            font-weight: 800;
            letter-spacing: 1px;
        }

        QLabel#capabilityChip {
            color: #7588AC;
            background: #0B1423;
            border: 1px solid #20314E;
            border-radius: 8px;
            padding: 5px 5px;
            font-size: 7px;
            font-weight: 800;
            letter-spacing: 0.7px;
        }

        QFrame#softDivider {
            color: #1D2C44;
            background: #1D2C44;
            border: none;
            max-height: 1px;
        }

        QProgressBar#processingBar {
            min-height: 2px;
            max-height: 2px;
            background: #121C2B;
            border: none;
            border-radius: 1px;
        }

        QProgressBar#processingBar::chunk {
            background: qlineargradient(
                x1: 0, y1: 0, x2: 1, y2: 0,
                stop: 0 #4F6FFF,
                stop: 0.55 #6B8AFF,
                stop: 1 #67E8F9
            );
            border-radius: 1px;
        }
    """
