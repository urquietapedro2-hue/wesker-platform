import sys

from PyQt5 import QtWidgets

from core.auth import SupabaseClient
from core.config import load_config
from ui.common import STYLE
from ui.login_window import LoginWindow
from ui.main_window import MainWindow


class App:
    def __init__(self):
        self.cfg = load_config()
        self.client = SupabaseClient(self.cfg["supabase_url"], self.cfg["supabase_anon_key"])
        self.login = self.main = None

    def show_login(self):
        self.login = LoginWindow(self.client, self.cfg, on_success=self.show_main)
        self.login.show()

    def show_main(self):
        self.main = MainWindow(self.client, self.cfg, on_logout=self.show_login)
        self.main.show()
        self.login.close()


def main():
    qt = QtWidgets.QApplication(sys.argv)
    qt.setStyleSheet(STYLE)
    App().show_login()
    sys.exit(qt.exec_())


if __name__ == "__main__":
    main()
