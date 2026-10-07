"""Devices — real device list with revoke support (Desktop / PySide6).

Phase 2 Product Refinement: replaces hardcoded mock data with real
GET /devices + DELETE /devices/{id}. Supports loading/empty/error states
and current-device highlighting.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QListWidget,
    QListWidgetItem,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QHBoxLayout,
    QMessageBox,
    QWidget,
)

from ...widgets.common import Page, primary_button
from ...theme import colors as C
from ...theme import typography as T
from ...errors.api_exception import ApiException
from .models import Device
from .repository import DeviceRepository


class DevicesPage(Page):
    def __init__(self, repository: DeviceRepository | None = None) -> None:
        super().__init__()
        self._repo = repository

        # Header
        head = QLabel("登录设备")
        head.setStyleSheet(
            f"font-size:{T.SIZE_TITLE}px;font-weight:{T.WEIGHT_BOLD};"
        )
        self.layout.addWidget(head)

        # Status label (loading/error)
        self._status = QLabel("")
        self._status.setStyleSheet(f"color:{C.TEXT_2};font-size:{T.SIZE_BODY}px;")
        self._status.setWordWrap(True)
        self.layout.addWidget(self._status)

        # Device list
        self._list = QListWidget()
        self._list.setStyleSheet(
            f"QListWidget{{background:{C.BG};border:1px solid {C.BORDER};"
            f"border-radius:{T.R_LG}px;}}"
            f"QListWidget::item{{padding:12px 16px;border-bottom:1px solid {C.BORDER};}}"
            f"QListWidget::item:selected{{background:{C.PRIMARY_LIGHT};}}"
        )
        self.layout.addWidget(self._list, 1)

        # Refresh button
        btn_row = QHBoxLayout()
        self._refresh_btn = primary_button("刷新")
        self._refresh_btn.clicked.connect(self.load_devices)
        btn_row.addWidget(self._refresh_btn)
        btn_row.addStretch()
        self.layout.addLayout(btn_row)

        # Auto-load on first show
        QTimer.singleShot(0, self.load_devices)

    def load_devices(self) -> None:
        if self._repo is None:
            self._status.setText("（无数据源）")
            return
        self._status.setText("加载中…")
        self._refresh_btn.setEnabled(False)
        self._list.clear()
        try:
            devices = self._repo.list()
            self._render_devices(devices)
            if not devices:
                self._status.setText("暂无登录设备")
            else:
                self._status.setText(f"共 {len(devices)} 台设备")
        except ApiException as e:
            self._status.setText(f"加载失败：{e.message}")
        except Exception as e:
            self._status.setText(f"加载失败：{str(e)}")
        finally:
            self._refresh_btn.setEnabled(True)

    def _render_devices(self, devices: list[Device]) -> None:
        for d in devices:
            item_widget = self._build_device_item(d)
            list_item = QListWidgetItem(self._list)
            list_item.setSizeHint(item_widget.sizeHint())
            self._list.addItem(list_item)
            self._list.setItemWidget(list_item, item_widget)

    def _build_device_item(self, device: Device) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(2)

        # Name + current badge
        name_row = QHBoxLayout()
        name = QLabel(device.display_name)
        name.setStyleSheet(
            f"font-size:{T.SIZE_BODY}px;font-weight:{T.WEIGHT_MEDIUM};"
            f"color:{C.TEXT};"
        )
        name_row.addWidget(name)
        if device.is_current:
            badge = QLabel("当前设备")
            badge.setStyleSheet(
                f"background:{C.PRIMARY_LIGHT};color:{C.PRIMARY};"
                f"padding:2px 8px;border-radius:8px;font-size:{T.SIZE_CAPTION}px;"
            )
            name_row.addWidget(badge)
        name_row.addStretch()
        lay.addLayout(name_row)

        # Details
        type_label = f"{device.device_type}"
        if device.device_identifier:
            type_label += f" · {device.device_identifier}"
        details = QLabel(type_label)
        details.setStyleSheet(f"color:{C.TEXT_2};font-size:{T.SIZE_CAPTION}px;")
        lay.addWidget(details)

        # Status + revoke
        status_row = QHBoxLayout()
        if device.is_online:
            status = QLabel("● 在线")
            status.setStyleSheet(f"color:{C.SUCCESS};font-size:{T.SIZE_CAPTION}px;")
        else:
            status = QLabel("● 已撤销")
            status.setStyleSheet(f"color:{C.TEXT_3};font-size:{T.SIZE_CAPTION}px;")
        status_row.addWidget(status)
        status_row.addStretch()

        if not device.is_current and device.is_online:
            revoke_btn = QPushButton("移除")
            revoke_btn.setStyleSheet(
                f"QPushButton{{color:{C.ERROR};border:1px solid {C.ERROR};"
                f"border-radius:{T.R_SM}px;padding:4px 12px;font-size:{T.SIZE_CAPTION}px;}}"
                f"QPushButton:hover{{background:{C.ERROR};color:#fff;}}"
            )
            revoke_btn.clicked.connect(lambda: self._confirm_revoke(device))
            status_row.addWidget(revoke_btn)
        lay.addLayout(status_row)

        return w

    def _confirm_revoke(self, device: Device) -> None:
        reply = QMessageBox.question(
            self,
            "移除设备",
            f"确定要移除设备「{device.display_name}」吗？\n移除后该设备将被强制登出。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        try:
            self._repo.revoke(device.id)
            QMessageBox.information(self, "已移除", f"设备「{device.display_name}」已移除。")
            self.load_devices()
        except ApiException as e:
            QMessageBox.warning(self, "移除失败", e.message)
        except Exception as e:
            QMessageBox.warning(self, "移除失败", str(e))
