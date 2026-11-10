"""Unical light theme (navy / gold) as a Qt stylesheet."""

NAVY = "#1F3864"
NAVY_DARK = "#16294A"
GOLD = "#C9A227"
BG = "#F4F6FA"
SURFACE = "#FFFFFF"
BORDER = "#D5DBE5"
TEXT = "#1E2430"
MUTED = "#5F6B7A"
RED = "#B42318"
AMBER = "#B54708"
GREEN = "#067647"

STYLESHEET = f"""
QWidget {{ font-family: 'Segoe UI', 'Calibri', Arial; font-size: 10pt; color: {TEXT}; }}
QMainWindow, QWidget#Page, QWidget#LoginBackground {{ background: {BG}; }}

/* ---------- sidebar ---------- */
QFrame#Sidebar {{ background: {NAVY}; }}
QLabel#SidebarTitle {{ color: white; font-size: 11pt; font-weight: 600; }}
QLabel#SidebarSub {{ color: #C9D3E6; font-size: 8.5pt; }}
QPushButton#NavButton {{
    color: #E6ECF7; background: transparent; border: none; text-align: left;
    padding: 10px 18px; font-size: 10pt; border-left: 4px solid transparent;
}}
QPushButton#NavButton:hover {{ background: {NAVY_DARK}; }}
QPushButton#NavButton:checked {{ background: {NAVY_DARK}; color: white; font-weight: 600; border-left: 4px solid {GOLD}; }}
QLabel#SidebarUser {{ color: #C9D3E6; font-size: 8.5pt; }}
QPushButton#LogoutButton {{ color: white; background: transparent; border: 1px solid #5A6E95; border-radius: 4px; padding: 6px; }}
QPushButton#LogoutButton:hover {{ background: {NAVY_DARK}; }}

/* ---------- headings ---------- */
QLabel#PageTitle {{ font-size: 17pt; font-weight: 600; color: {NAVY}; }}
QLabel#PageSubtitle {{ color: {MUTED}; }}
QLabel#SectionTitle {{ font-size: 11pt; font-weight: 600; color: {NAVY}; }}
QFrame#GoldRule {{ background: {GOLD}; max-height: 3px; min-height: 3px; }}

/* ---------- cards ---------- */
QFrame#Card {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 8px; }}
QLabel#CardValue {{ font-size: 24pt; font-weight: 600; color: {NAVY}; }}
QLabel#CardLabel {{ color: {MUTED}; font-size: 9pt; }}
QFrame#CardAccent {{ background: {GOLD}; min-width: 4px; max-width: 4px; border-radius: 2px; }}

/* ---------- buttons ---------- */
QPushButton {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 5px; padding: 7px 14px; }}
QPushButton:hover {{ border-color: {NAVY}; }}
QPushButton:disabled {{ color: #9AA4B2; }}
QPushButton#PrimaryButton {{ background: {NAVY}; color: white; border: 1px solid {NAVY}; font-weight: 600; }}
QPushButton#PrimaryButton:hover {{ background: {NAVY_DARK}; }}
QPushButton#PrimaryButton:disabled {{ background: #8A9AB8; border-color: #8A9AB8; }}

/* ---------- inputs ---------- */
QLineEdit {{ background: white; border: 1px solid {BORDER}; border-radius: 5px; padding: 8px; }}
QLineEdit:focus {{ border: 1px solid {NAVY}; }}
QCheckBox {{ color: {MUTED}; }}

/* ---------- tables ---------- */
QTableWidget {{ background: white; border: 1px solid {BORDER}; border-radius: 6px; gridline-color: #EEF1F5;
               selection-background-color: #DCE4F2; selection-color: {TEXT}; }}
QHeaderView::section {{ background: {NAVY}; color: white; padding: 6px; border: none; font-weight: 600; }}

/* ---------- login ---------- */
QFrame#LoginCard {{ background: white; border: 1px solid {BORDER}; border-radius: 10px; }}
QLabel#LoginAppName {{ font-size: 14pt; font-weight: 600; color: {NAVY}; }}
QLabel#LoginError {{ color: {RED}; }}
QLabel#Footnote {{ color: {MUTED}; font-size: 8pt; }}
QLabel#Banner {{ background: #FFF6DB; border: 1px solid #F1D98A; border-radius: 5px; padding: 8px; color: #6B4E00; }}
"""
