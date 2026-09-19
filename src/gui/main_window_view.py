from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QActionGroup, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFrame,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QSplitter,
    QToolButton,
    QTreeWidget,
    QVBoxLayout,
    QWidget,
)

from config.settings import resource_path, save_settings
from gui.theme import apply_theme


class MainWindowViewMixin:
    def _build_ui(self) -> None:
        self.tree = QTreeWidget()
        self.tree.setObjectName("mainTree")
        self.tree.setColumnCount(14)
        self.tree.setHeaderHidden(True)
        self.tree.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tree.itemDoubleClicked.connect(self._edit_selected)
        self.tree.itemSelectionChanged.connect(self._tree_selection_changed)
        for column in range(1, 14):
            self.tree.setColumnHidden(column, True)

        self.device_table = QTreeWidget()
        self.device_table.setObjectName("deviceTable")
        self.device_table.setColumnCount(16)
        self.device_table.setRootIsDecorated(False)
        self.device_table.setItemsExpandable(False)
        self.device_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.device_table.setAlternatingRowColors(True)
        self.device_table.setSortingEnabled(True)
        self.device_table.itemDoubleClicked.connect(self._edit_selected)
        self.device_table.itemSelectionChanged.connect(self._table_selection_changed)
        header = self.device_table.header()
        header.setStretchLastSection(False)
        for column in range(16):
            header.setSectionResizeMode(column, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        self.device_table.setColumnHidden(3, True)

        self.add_branch_button = QPushButton()
        self.add_mango_button = QPushButton()
        self.edit_button = QPushButton()
        self.certificate_button = QPushButton()
        self.export_button = QPushButton()
        self.export_button.setObjectName("primaryButton")
        self.add_branch_button.clicked.connect(self.add_branch)
        self.add_mango_button.clicked.connect(self.add_mango)
        self.edit_button.clicked.connect(self._edit_selected)
        self.certificate_button.clicked.connect(self.manage_certificates)
        self.export_button.clicked.connect(self.export_configs)

        self.delete_branch_action = QAction(self)
        self.delete_mango_action = QAction(self)
        self.xlsx_action = QAction(self)
        self.delete_branch_action.triggered.connect(self.delete_branch)
        self.delete_mango_action.triggered.connect(self.delete_mango)
        self.xlsx_action.triggered.connect(self.export_list)
        self.more_button = QToolButton()
        self.more_button.setPopupMode(QToolButton.InstantPopup)
        self.more_menu = QMenu(self.more_button)
        self.more_menu.addAction(self.delete_branch_action)
        self.more_menu.addAction(self.delete_mango_action)
        self.more_menu.addSeparator()
        self.more_menu.addAction(self.xlsx_action)
        self.more_button.setMenu(self.more_menu)

        tools = QHBoxLayout()
        tools.setContentsMargins(0, 0, 0, 0)
        tools.setSpacing(6)
        for button in (self.add_branch_button, self.add_mango_button, self.edit_button):
            tools.addWidget(button)
        tools.addWidget(self.more_button)
        tools.addStretch()
        tools.addWidget(self.certificate_button)
        tools.addWidget(self.export_button)

        self.header = QFrame()
        self.header.setObjectName("brandHeader")
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(10, 5, 10, 5)
        header_layout.setSpacing(8)
        logo_label = QLabel()
        logo_label.setFixedSize(30, 30)
        logo_label.setAlignment(Qt.AlignCenter)
        logo = QPixmap(str(resource_path("icons", "mb-soft.png")))
        if not logo.isNull():
            logo_label.setPixmap(
                logo.scaled(28, 28, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )
        header_layout.addWidget(logo_label)
        self.brand_title_label = QLabel()
        self.brand_title_label.setObjectName("brandTitle")
        header_layout.addWidget(self.brand_title_label)
        header_layout.addStretch()

        self.workflow_frame = QFrame()
        self.workflow_frame.setObjectName("workflowPanel")
        workflow_layout = QHBoxLayout(self.workflow_frame)
        workflow_layout.setContentsMargins(10, 5, 10, 5)
        workflow_layout.setSpacing(8)
        self.workflow_summary_label = QLabel()
        self.workflow_summary_label.setObjectName("workflowSummary")
        self.next_step_button = QPushButton()
        self.next_step_button.clicked.connect(self._run_next_workflow_step)
        workflow_layout.addWidget(self.workflow_summary_label, 1)
        workflow_layout.addWidget(self.next_step_button)

        branch_panel = QWidget()
        branch_layout = QVBoxLayout(branch_panel)
        branch_layout.setContentsMargins(0, 0, 0, 0)
        branch_layout.setSpacing(4)
        self.all_mangos_button = QPushButton()
        self.all_mangos_button.setObjectName("scopeButton")
        self.all_mangos_button.setCheckable(True)
        self.all_mangos_button.setChecked(True)
        self.all_mangos_button.clicked.connect(self._select_all_mangos)
        branch_layout.addWidget(self.all_mangos_button)
        branch_layout.addWidget(self.tree, 1)

        self.workspace_splitter = QSplitter(Qt.Horizontal)
        self.workspace_splitter.setObjectName("workspaceSplitter")
        self.workspace_splitter.addWidget(branch_panel)
        self.workspace_splitter.addWidget(self.device_table)
        self.workspace_splitter.setSizes([205, 1020])
        self.workspace_splitter.setStretchFactor(0, 0)
        self.workspace_splitter.setStretchFactor(1, 1)
        self.workspace_splitter.setCollapsible(1, False)

        status_bar = self.statusBar()
        self.server_status_title = QLabel()
        self.server_status_value = QLabel()
        self.server_status_value.setObjectName("runtimeStatus")
        self.server_status_value.setProperty("state", "unknown")
        self.server_status_value.setToolTip(str(self.runtime.status_path))
        self.count_status_label = QLabel()
        self.selection_status_label = QLabel()
        status_bar.addWidget(self.server_status_title)
        status_bar.addWidget(self.server_status_value)
        status_bar.addPermanentWidget(self.count_status_label)
        status_bar.addPermanentWidget(self.selection_status_label)

        central_layout = QVBoxLayout()
        central_layout.setContentsMargins(8, 8, 8, 6)
        central_layout.setSpacing(6)
        central_layout.addWidget(self.header)
        central_layout.addWidget(self.workflow_frame)
        central_layout.addLayout(tools)
        central_layout.addWidget(self.workspace_splitter, 1)
        central = QWidget()
        central.setLayout(central_layout)
        self.setCentralWidget(central)

        self.language_menu = self.menuBar().addMenu("")
        language_group = QActionGroup(self)
        language_group.setExclusive(True)
        self.english_action = QAction("English", self, checkable=True)
        self.german_action = QAction("Deutsch", self, checkable=True)
        self.english_action.setData("en")
        self.german_action.setData("de")
        for action in (self.english_action, self.german_action):
            language_group.addAction(action)
            self.language_menu.addAction(action)
            action.triggered.connect(lambda checked, a=action: self.set_language(a.data()))

        self.appearance_menu = self.menuBar().addMenu("")
        theme_group = QActionGroup(self)
        theme_group.setExclusive(True)
        self.light_theme_action = QAction("", self, checkable=True)
        self.dark_theme_action = QAction("", self, checkable=True)
        self.light_theme_action.setData("light")
        self.dark_theme_action.setData("dark")
        for action in (self.light_theme_action, self.dark_theme_action):
            theme_group.addAction(action)
            self.appearance_menu.addAction(action)
            action.triggered.connect(lambda checked, a=action: self.set_theme(a.data()))

        self.setup_menu = self.menuBar().addMenu("")
        self.setup_action = QAction(self)
        self.setup_action.triggered.connect(self.show_setup)
        self.setup_menu.addAction(self.setup_action)
        self.resize(1250, 740)

    def _retranslate(self) -> None:
        self.setWindowTitle(f'{self.t("app_title")} — {self.build_info.version}')
        if hasattr(self, "update_controller"):
            self.update_controller.retranslate()
        labels = (
            (self.brand_title_label, "app_title"),
            (self.add_branch_button, "add_branch"),
            (self.add_mango_button, "add_mango"),
            (self.edit_button, "edit_selection"),
            (self.certificate_button, "certificates"),
            (self.export_button, "export"),
            (self.more_button, "more_actions"),
            (self.all_mangos_button, "all_mangos"),
            (self.server_status_title, "server_live_status"),
        )
        for widget, key in labels:
            widget.setText(self.t(key))
        self.delete_branch_action.setText(self.t("delete_branch"))
        self.delete_mango_action.setText(self.t("delete_mango"))
        self.xlsx_action.setText(self.t("export_list"))
        self.language_menu.setTitle(self.t("language"))
        self.appearance_menu.setTitle(self.t("appearance"))
        self.setup_menu.setTitle(self.t("setup"))
        self.setup_action.setText(self.t("open_setup"))
        self.light_theme_action.setText(self.t("light_theme"))
        self.dark_theme_action.setText(self.t("dark_theme"))
        export_headers = [
            "name", "description", "vpn_ip", "lan_network", "mango_ip", "oven_ip",
            "oven_subnet_mask", "oven_gateway", "certificate", "configuration",
            "connection", "connected_since", "remote_ip", "last_seen",
        ]
        table_headers = [
            "name", "branch", "description", "internal_id", "vpn_ip", "lan_network",
            "mango_ip", "oven_ip", "oven_subnet_mask", "oven_gateway", "certificate",
            "configuration", "connection", "connected_since", "remote_ip", "last_seen",
        ]
        self.tree.setHeaderLabels([self.t(key) for key in export_headers])
        self.device_table.setHeaderLabels([self.t(key) for key in table_headers])
        self.english_action.setChecked(self.settings.language == "en")
        self.german_action.setChecked(self.settings.language == "de")
        self.light_theme_action.setChecked(self.settings.theme == "light")
        self.dark_theme_action.setChecked(self.settings.theme == "dark")

    def set_theme(self, theme: str) -> None:
        if theme not in {"light", "dark"}:
            return
        self.settings.theme = theme
        application = QApplication.instance()
        if application is not None:
            apply_theme(application, theme)
        save_settings(self.settings)
        self._retranslate()
        self.reload_tree()

    def set_language(self, language: str) -> None:
        self.settings.language = language
        self.translator.set_language(language)
        save_settings(self.settings)
        self._retranslate()
        self.reload_tree()
