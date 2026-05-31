"""
Tripadvisor portal — website inside this window, capture email only.
No separate Chrome window.
"""

from __future__ import annotations

import sys
from urllib.parse import urlparse

from PyQt6.QtCore import QUrl
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from email_parser import ALLOWED_DOMAIN, extract_emails, is_tripadvisor_url

try:
    from PyQt6.QtWebEngineWidgets import QWebEngineView
except ImportError:
    print("Install: pip install PyQt6 PyQt6-WebEngine")
    sys.exit(1)

DEFAULT_URL = "https://www.tripadvisor.com/"


class PortalApp(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Tripadvisor Portal — email only")
        self.resize(1100, 750)

        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)

        # Top bar
        bar = QHBoxLayout()
        bar.addWidget(QLabel("URL"))
        self.url_input = QLineEdit(DEFAULT_URL)
        bar.addWidget(self.url_input, stretch=1)
        go_btn = QPushButton("Go")
        go_btn.clicked.connect(self._on_go)
        bar.addWidget(go_btn)
        cap_btn = QPushButton("Capture email")
        cap_btn.setStyleSheet("font-weight: bold; padding: 6px 14px;")
        cap_btn.clicked.connect(self._on_capture)
        bar.addWidget(cap_btn)
        layout.addLayout(bar)

        self.status = QLabel("Browse inside the portal below — then click Capture email.")
        self.status.setStyleSheet("color: #444;")
        layout.addWidget(self.status)

        # Embedded browser (portal)
        self.web = QWebEngineView()
        self.web.setUrl(QUrl(DEFAULT_URL))
        self.web.urlChanged.connect(self._on_url_changed)
        layout.addWidget(self.web, stretch=1)

        # Email result
        layout.addWidget(QLabel("Email captured from current page"))
        self.email_box = QTextEdit()
        self.email_box.setMaximumHeight(80)
        self.email_box.setReadOnly(True)
        self.email_box.setPlaceholderText("No email yet…")
        layout.addWidget(self.email_box)

        self._emails_found: list[str] = []

    def _on_url_changed(self, url: QUrl) -> None:
        s = url.toString()
        if is_tripadvisor_url(s):
            self.url_input.setText(s)
            self.status.setText("On Tripadvisor — open a page, then Capture email.")
        elif s and s != "about:blank":
            self.status.setText(f"⚠ Only {ALLOWED_DOMAIN} allowed — blocked navigation.")

    def _on_go(self) -> None:
        raw = self.url_input.text().strip()
        if not raw:
            return
        if not raw.startswith(("http://", "https://")):
            raw = "https://" + raw
        if not is_tripadvisor_url(raw):
            QMessageBox.warning(
                self,
                "Not allowed",
                f"Only {ALLOWED_DOMAIN} links can be opened in this portal.",
            )
            return
        self.web.setUrl(QUrl(raw))

    def _on_capture(self) -> None:
        url = self.web.url().toString()
        if not is_tripadvisor_url(url):
            QMessageBox.warning(
                self,
                "Not Tripadvisor",
                "Current page is not Tripadvisor. Navigate to tripadvisor.com first.",
            )
            return
        self.status.setText("Reading page…")
        self.web.page().toHtml(self._handle_html)

    def _handle_html(self, html: str) -> None:
        url = self.web.url().toString()
        if "please enable js" in html.lower()[:2000]:
            self.status.setText("⚠ Page blocked or JS not loaded — wait, then try again.")
            self.email_box.setPlainText(
                "Tripadvisor blocked this view.\n"
                "Wait for the full page to load, or open a different listing."
            )
            return

        emails = extract_emails(html)
        self._emails_found = emails

        if emails:
            text = "\n".join(emails)
            self.email_box.setPlainText(text)
            self.status.setText(f"Found {len(emails)} email(s) on this page.")
        else:
            self.email_box.setPlainText(
                "(none)\n\nTripadvisor rarely shows emails on public pages.\n"
                "Try the restaurant website link on the listing."
            )
            self.status.setText("No email on this page.")


def main() -> None:
    app = QApplication(sys.argv)
    win = PortalApp()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
