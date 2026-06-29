#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
模型可用性测试工具
支持多提供商管理、拉取模型、批量测试
"""

import concurrent.futures
import json
import os
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, simpledialog
from datetime import datetime

import requests


class ProviderDialog(tk.Toplevel):
    """添加/编辑提供商的对话框"""
    def __init__(self, parent, title="添加提供商", provider=None):
        super().__init__(parent)
        self.title(title)
        self.geometry("520x220")
        self.resizable(False, False)
        self.result = None
        self.provider = provider

        c = parent.colors if hasattr(parent, 'colors') else {}
        bg = c.get("bg", "#1e1e2e")
        fg = c.get("fg", "#cdd6f4")
        entry_bg = c.get("entry_bg", "#313244")
        self.configure(bg=bg)

        frame = ttk.Frame(self, padding=16)
        frame.pack(fill=tk.BOTH, expand=True)

        # Name
        row0 = ttk.Frame(frame)
        row0.pack(fill=tk.X, pady=4)
        ttk.Label(row0, text="提供商名称:", width=12).pack(side=tk.LEFT)
        self.name_var = tk.StringVar(value=provider["name"] if provider else "")
        name_entry = ttk.Entry(row0, textvariable=self.name_var)
        name_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        name_entry.focus_set()

        # URL
        row1 = ttk.Frame(frame)
        row1.pack(fill=tk.X, pady=4)
        ttk.Label(row1, text="API 地址:", width=12).pack(side=tk.LEFT)
        self.url_var = tk.StringVar(value=provider["url"] if provider else "https://api.deepseek.com/v1")
        ttk.Entry(row1, textvariable=self.url_var).pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Key
        row2 = ttk.Frame(frame)
        row2.pack(fill=tk.X, pady=4)
        ttk.Label(row2, text="API Key:", width=12).pack(side=tk.LEFT)
        self.key_var = tk.StringVar(value=provider["key"] if provider else "")
        key_entry = ttk.Entry(row2, textvariable=self.key_var, show="*")
        key_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Buttons
        btn_row = ttk.Frame(frame)
        btn_row.pack(fill=tk.X, pady=(12, 0))
        ttk.Button(btn_row, text="取消", command=self.destroy).pack(side=tk.RIGHT, padx=4)
        ttk.Button(btn_row, text="保存", command=self.on_save).pack(side=tk.RIGHT, padx=4)

        self.transient(parent)
        self.grab_set()
        self.wait_window()

    def on_save(self):
        name = self.name_var.get().strip()
        url = self.url_var.get().strip().rstrip("/")
        key = self.key_var.get().strip()
        if not name:
            messagebox.showwarning("提示", "请输入提供商名称", parent=self)
            return
        if not url:
            messagebox.showwarning("提示", "请输入 API 地址", parent=self)
            return
        if not key:
            messagebox.showwarning("提示", "请输入 API Key", parent=self)
            return
        self.result = {"name": name, "url": url, "key": key}
        self.destroy()


class ModelTesterApp:
    """OpenAI 兼容 API 模型测试工具（多提供商版）"""

    def __init__(self, root):
        self.root = root
        self.root.title("模型可用性测试工具-------暖君api开放平台提供。严禁盗用")
        self.root.geometry("1350x850")
        self.root.minsize(1000, 700)

        # ── 数据 ──
        self.providers = []           # [{"name":..., "url":..., "key":...}]
        self.selected_providers = set()  # 勾选的提供商 name
        self.models = []              # [{"id":..., "provider":...}]
        self.selected_models = set()  # 勾选的模型 id
        self.testing = False
        self.stop_testing = False
        self.config_path = os.path.join(os.path.dirname(__file__), "providers_config.json")

        self.setup_styles()
        self.build_ui()
        self.load_providers()  # 自动加载已保存的配置
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    # ──────────────── 样式 ────────────────

    def setup_styles(self):
        style = ttk.Style()
        style.theme_use("clam")
        bg = "#1e1e2e"
        fg = "#cdd6f4"
        select_bg = "#45475a"
        entry_bg = "#313244"
        accent = "#89b4fa"
        error_color = "#f38ba8"
        success_color = "#a6e3a1"

        style.configure("TFrame", background=bg)
        style.configure("TLabel", background=bg, foreground=fg, font=("Segoe UI", 10))
        style.configure("TButton",
                        background=accent, foreground=bg,
                        font=("Segoe UI", 10, "bold"),
                        borderwidth=0, focusthickness=0, padding=(10, 5))
        style.map("TButton",
                  background=[("active", "#74c7ec"), ("disabled", "#585b70")],
                  foreground=[("disabled", "#6c7086")])
        style.configure("Success.TLabel", foreground=success_color, background=bg)
        style.configure("Error.TLabel", foreground=error_color, background=bg)
        style.configure("TEntry",
                        fieldbackground=entry_bg, foreground=fg,
                        borderwidth=1, font=("Segoe UI", 10), padding=4)
        style.configure("TCombobox",
                        fieldbackground=entry_bg, foreground=fg,
                        arrowcolor=fg, borderwidth=1)
        style.map("TCombobox", fieldbackground=[("readonly", entry_bg)])
        style.configure("Vertical.TScrollbar",
                        background="#45475a", troughcolor=bg,
                        arrowcolor=fg, borderwidth=0)
        style.configure("Treeview",
                        background=entry_bg, foreground=fg,
                        fieldbackground=entry_bg, borderwidth=0,
                        font=("Segoe UI", 10))
        style.map("Treeview",
                  background=[("selected", select_bg)],
                  foreground=[("selected", fg)])
        style.configure("Treeview.Heading",
                        background="#45475a", foreground=fg,
                        font=("Segoe UI", 10, "bold"), borderwidth=1)

        self.colors = {
            "bg": bg, "fg": fg, "entry_bg": entry_bg,
            "accent": accent, "select_bg": select_bg,
            "success": success_color, "error": error_color,
        }

    # ──────────────── UI 构建 ────────────────

    def build_ui(self):
        c = self.colors
        root = self.root
        root.configure(bg=c["bg"])

        # ── 顶部：测试 Prompt ──
        top = ttk.Frame(root)
        top.pack(fill=tk.X, padx=16, pady=(12, 4))
        ttk.Label(top, text="测试 Prompt:").pack(side=tk.LEFT)
        self.prompt_var = tk.StringVar(value="hi")
        ttk.Entry(top, textvariable=self.prompt_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 0))

        # ── 主区域：左(提供商列表) 中(模型列表) 右(结果) ──
        main_paned = ttk.PanedWindow(root, orient=tk.HORIZONTAL)
        main_paned.pack(fill=tk.BOTH, expand=True, padx=16, pady=4)

        # ── 左：提供商列表 ──
        left_frame = ttk.Frame(main_paned)
        self.build_provider_panel(left_frame)
        main_paned.add(left_frame, weight=1)

        # ── 中：模型列表（weight=2 分配更多空间）──
        mid_frame = ttk.Frame(main_paned)
        self.build_model_panel(mid_frame)
        main_paned.add(mid_frame, weight=2)

        # ── 右：结果 ──
        right_frame = ttk.Frame(main_paned)
        ttk.Label(right_frame, text="测试结果", font=("Segoe UI", 11, "bold")).pack(anchor=tk.W, pady=(0, 4))
        self.result_text = scrolledtext.ScrolledText(
            right_frame,
            bg=c["entry_bg"], fg=c["fg"],
            insertbackground=c["fg"],
            font=("Consolas", 10),
            borderwidth=0, wrap=tk.WORD,
            state=tk.DISABLED,
        )
        self.result_text.pack(fill=tk.BOTH, expand=True)
        main_paned.add(right_frame, weight=1)

        # ── 底：状态栏 ──
        self.status_bar = ttk.Label(root, text="就绪", anchor=tk.W, font=("Segoe UI", 9))
        self.status_bar.pack(fill=tk.X, padx=16, pady=(4, 8))

    # ──────────────── 提供商面板 ────────────────

    def build_provider_panel(self, parent):
        c = self.colors
        ttk.Label(parent, text="提供商列表", font=("Segoe UI", 11, "bold")).pack(anchor=tk.W, pady=(0, 4))

        # 全选
        sel_row = ttk.Frame(parent)
        sel_row.pack(fill=tk.X, pady=(0, 4))
        self.prov_select_all_var = tk.BooleanVar()
        self.prov_select_all_cb = ttk.Checkbutton(sel_row, text="全选",
                                                   variable=self.prov_select_all_var,
                                                   command=self.toggle_prov_select_all)
        self.prov_select_all_cb.pack(side=tk.LEFT)
        self.prov_count_label = ttk.Label(sel_row, text="(0)")
        self.prov_count_label.pack(side=tk.LEFT, padx=4)

        # Treeview
        tree_frame = ttk.Frame(parent)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        self.prov_tree = ttk.Treeview(tree_frame, columns=(), show="tree", height=10)
        self.prov_tree.heading("#0", text="提供商")
        self.prov_tree.column("#0", width=200, minwidth=150, stretch=True)
        vscrolly = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.prov_tree.yview)
        self.prov_tree.configure(yscrollcommand=vscrolly.set)
        self.prov_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vscrolly.pack(side=tk.RIGHT, fill=tk.Y)
        self.prov_tree.bind("<ButtonRelease-1>", self.on_prov_click)

        # 操作按钮
        btn_row = ttk.Frame(parent)
        btn_row.pack(fill=tk.X, pady=(6, 0))
        ttk.Button(btn_row, text="+ 添加", command=self.add_provider, width=8).pack(side=tk.LEFT, padx=(0, 4))
        self.edit_prov_btn = ttk.Button(btn_row, text="✎ 编辑", command=self.edit_provider, width=8, state=tk.DISABLED)
        self.edit_prov_btn.pack(side=tk.LEFT, padx=2)
        self.del_prov_btn = ttk.Button(btn_row, text="✕ 删除", command=self.delete_provider, width=8, state=tk.DISABLED)
        self.del_prov_btn.pack(side=tk.LEFT, padx=2)

        # 分隔 + 操作按钮
        ttk.Separator(parent, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=8)

        self.fetch_btn = ttk.Button(parent, text="📥 拉取选中提供商模型",
                                    command=self.fetch_selected_providers, state=tk.DISABLED)
        self.fetch_btn.pack(fill=tk.X, pady=2)

        self.test_selected_btn = ttk.Button(parent, text="▶ 测试选中模型",
                                            command=self.test_selected, state=tk.DISABLED)
        self.test_selected_btn.pack(fill=tk.X, pady=2)

        self.test_all_btn = ttk.Button(parent, text="▶▶ 测试全部模型",
                                       command=self.test_all, state=tk.DISABLED)
        self.test_all_btn.pack(fill=tk.X, pady=2)

        self.stop_btn = ttk.Button(parent, text="⏹ 停止测试",
                                   command=self.request_stop, state=tk.DISABLED)
        self.stop_btn.pack(fill=tk.X, pady=2)

    # ──────────────── 模型面板 ────────────────

    def build_model_panel(self, parent):
        ttk.Label(parent, text="模型列表", font=("Segoe UI", 11, "bold")).pack(anchor=tk.W, pady=(0, 4))

        sel_row = ttk.Frame(parent)
        sel_row.pack(fill=tk.X, pady=(0, 4))
        self.model_select_all_var = tk.BooleanVar()
        self.model_select_all_cb = ttk.Checkbutton(sel_row, text="全选",
                                                    variable=self.model_select_all_var,
                                                    command=self.toggle_model_select_all,
                                                    state=tk.DISABLED)
        self.model_select_all_cb.pack(side=tk.LEFT)
        self.model_count_label = ttk.Label(sel_row, text="(0 个)")
        self.model_count_label.pack(side=tk.LEFT, padx=4)
        self.pass_count_label = ttk.Label(sel_row, foreground=self.colors["success"], text="")
        self.pass_count_label.pack(side=tk.LEFT, padx=(8, 2))
        self.fail_count_label = ttk.Label(sel_row, foreground=self.colors["error"], text="")
        self.fail_count_label.pack(side=tk.LEFT, padx=2)

        tree_frame = ttk.Frame(parent)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        # 列: 勾选 | 序号 | 提供商 | 模型名 | 状态
        self.model_tree = ttk.Treeview(
            tree_frame,
            columns=("check", "seq", "provider", "name", "status"),
            show="headings",
            height=22,
        )
        self.model_tree.heading("check", text="✓")
        self.model_tree.heading("seq", text="#")
        self.model_tree.heading("provider", text="提供商")
        self.model_tree.heading("name", text="模型名称")
        self.model_tree.heading("status", text="测试状态")
        self.model_tree.column("check", width=40, anchor=tk.CENTER, stretch=False)
        self.model_tree.column("seq", width=40, anchor=tk.CENTER, stretch=False)
        self.model_tree.column("provider", width=120, anchor=tk.W, stretch=False)
        self.model_tree.column("name", width=260, minwidth=180, stretch=True)
        self.model_tree.column("status", width=150, anchor=tk.CENTER, stretch=False, minwidth=130)

        # 隐藏 #0 列
        self.model_tree.column("#0", width=0, minwidth=0, stretch=False)

        vscrolly = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.model_tree.yview)
        self.model_tree.configure(yscrollcommand=vscrolly.set)
        self.model_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vscrolly.pack(side=tk.RIGHT, fill=tk.Y)

        self.model_tree.bind("<ButtonRelease-1>", self.on_model_click)
        self.model_tree.bind("<Double-1>", self.on_model_double_click)

    # ──────────────── 提供商操作 ────────────────

    def add_provider(self):
        dlg = ProviderDialog(self.root, title="添加提供商")
        if dlg.result:
            self.providers.append(dlg.result)
            self.refresh_prov_tree()
            self.save_providers()
            self.log(f"📋 已添加提供商: {dlg.result['name']} ({dlg.result['url']})")

    def edit_provider(self):
        sel = self.get_single_selected_provider()
        if not sel:
            return
        idx, prov = sel
        old_name = prov["name"]
        dlg = ProviderDialog(self.root, title=f"编辑提供商 - {old_name}", provider=prov)
        if dlg.result:
            # 如果名称变了，更新 models 中的 provider 名
            if dlg.result["name"] != old_name:
                for m in self.models:
                    if m["provider"] == old_name:
                        m["provider"] = dlg.result["name"]
            self.providers[idx] = dlg.result
            self.refresh_prov_tree()
            self.refresh_model_tree()
            self.save_providers()
            self.log(f"✎ 已更新提供商: {old_name} → {dlg.result['name']}")

    def delete_provider(self):
        sel = self.get_single_selected_provider()
        if not sel:
            return
        idx, prov = sel
        if not messagebox.askyesno("确认", f"确定删除提供商「{prov['name']}」？\n相关模型也会被清除。"):
            return
        self.providers.pop(idx)
        self.models = [m for m in self.models if m["provider"] != prov["name"]]
        self.selected_models = {m for m in self.selected_models if m in [x["id"] for x in self.models]}
        self.selected_providers.discard(prov["name"])
        self.refresh_prov_tree()
        self.refresh_model_tree()
        self.save_providers()
        self.log(f"🗑 已删除提供商: {prov['name']}")

    def get_single_selected_provider(self):
        """获取提供商列表中单个选中项。返回 (index, provider) 或 None"""
        sel = self.prov_tree.selection() if hasattr(self.prov_tree, 'selection') else ()
        if not sel:
            messagebox.showinfo("提示", "请先选择一个提供商")
            return None
        iid = sel[0]
        for idx, prov in enumerate(self.providers):
            if prov["name"] == iid:
                return idx, prov
        return None

    def toggle_prov_select_all(self):
        if self.prov_select_all_var.get():
            self.selected_providers = set(p["name"] for p in self.providers)
        else:
            self.selected_providers.clear()
        self.refresh_prov_tree()

    def on_prov_click(self, event):
        item = self.prov_tree.focus()
        if not item:
            return
        if item in self.selected_providers:
            self.selected_providers.discard(item)
        else:
            self.selected_providers.add(item)
        # 更新显示
        self.prov_tree.item(item, text=f"{'✅' if item in self.selected_providers else '⬜'}  {item}")
        self.prov_select_all_var.set(len(self.selected_providers) == len(self.providers) > 0)
        # 启用/禁用编辑删除按钮（单选时可用）
        sel = self.prov_tree.selection()
        has_single = len(sel) == 1 and sel[0] in [p["name"] for p in self.providers]
        self.edit_prov_btn.configure(state=tk.NORMAL if has_single else tk.DISABLED)
        self.del_prov_btn.configure(state=tk.NORMAL if has_single else tk.DISABLED)

    def refresh_prov_tree(self):
        self.prov_tree.delete(*self.prov_tree.get_children())
        for p in self.providers:
            checked = "✅" if p["name"] in self.selected_providers else "⬜"
            iid = p["name"]
            self.prov_tree.insert("", tk.END, iid=iid, text=f"{checked}  {p['name']}")
        self.prov_select_all_var.set(len(self.selected_providers) == len(self.providers) > 0)
        self.prov_count_label.configure(text=f"({len(self.providers)})")
        self.fetch_btn.configure(state=tk.NORMAL if self.providers else tk.DISABLED)

    # ──────────────── 配置持久化 ────────────────

    def save_providers(self):
        """保存提供商配置到 JSON 文件"""
        data = {
            "providers": self.providers,
            "selected": list(self.selected_providers),
        }
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存配置失败: {e}")

    def load_providers(self):
        """从 JSON 文件加载提供商配置"""
        if not os.path.exists(self.config_path):
            return
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.providers = data.get("providers", [])
            self.selected_providers = set(data.get("selected", []))
            # 过滤掉已删除提供商的选中状态
            valid_names = {p["name"] for p in self.providers}
            self.selected_providers &= valid_names
            self.refresh_prov_tree()
            if self.providers:
                self.log(f"📂 已自动加载 {len(self.providers)} 个提供商配置")
        except Exception as e:
            print(f"加载配置失败: {e}")

    # ──────────────── 模型列表操作 ────────────────

    def toggle_model_select_all(self):
        if self.model_select_all_var.get():
            self.selected_models = set(m["id"] for m in self.models)
        else:
            self.selected_models.clear()
        self.refresh_model_tree()

    def on_model_click(self, event):
        # 判断点击的是哪列
        region = self.model_tree.identify_region(event.x, event.y)
        if region == "heading":
            return
        col = self.model_tree.identify_column(event.x)

        item_iid = self.model_tree.identify_row(event.y)
        if not item_iid:
            return

        # #2 = seq 列 → 单模型测试
        if col == "#2":  # seq 列
            self.selected_models = {item_iid}
            self._sync_model_tree_display()
            self.test_selected()
            return

        # 点击其他列 → 切换选中
        if item_iid in self.selected_models:
            self.selected_models.discard(item_iid)
        else:
            self.selected_models.add(item_iid)

        self._sync_model_tree_display()
        self.model_select_all_var.set(len(self.selected_models) == len(self.models) > 0)

    def on_model_double_click(self, event):
        item_iid = self.model_tree.identify_row(event.y)
        if not item_iid:
            return
        self.selected_models = {item_iid}
        self._sync_model_tree_display()
        self.test_selected()

    def refresh_model_tree(self):
        self.model_tree.delete(*self.model_tree.get_children())
        for idx, m in enumerate(self.models, 1):
            checked = "✅" if m["id"] in self.selected_models else "⬜"
            iid = m["id"]
            self.model_tree.insert(
                "", tk.END, iid=iid, text="",
                values=(checked, idx, m["provider"], m["id"], ""),
            )
        self.model_select_all_var.set(len(self.selected_models) == len(self.models) > 0)
        self.model_select_all_cb.configure(state=tk.NORMAL if self.models else tk.DISABLED)
        self.model_count_label.configure(text=f"({len(self.models)} 个)")
        self.test_selected_btn.configure(state=tk.NORMAL if self.models else tk.DISABLED)
        self.test_all_btn.configure(state=tk.NORMAL if self.models else tk.DISABLED)

    def _sync_model_tree_display(self):
        """刷新勾选状态显示，不重建树"""
        for child in self.model_tree.get_children():
            checked = "✅" if child in self.selected_models else "⬜"
            self.model_tree.set(child, "check", checked)

    # ──────────────── 拉取模型 ────────────────

    def fetch_selected_providers(self):
        if not self.selected_providers:
            messagebox.showinfo("提示", "请先勾选要拉取模型的提供商（单击勾选）")
            return

        provs = [p for p in self.providers if p["name"] in self.selected_providers]
        if not provs:
            return

        self.fetch_btn.configure(state=tk.DISABLED)
        self.set_buttons_fetching(True)
        self.log(f"📡 开始拉取 {len(provs)} 个提供商的模型列表...")

        def do_fetch_all():
            total_new = 0
            errors = []
            all_models = []

            # 清空旧模型
            self.models.clear()
            self.selected_models.clear()

            for prov in provs:
                self.root.after(0, lambda msg=f"拉取 {prov['name']}...": self.set_status(msg))
                try:
                    resp = requests.get(
                        f"{prov['url']}/models",
                        headers={"Authorization": f"Bearer {prov['key']}"},
                        timeout=30,
                    )
                    if resp.status_code != 200:
                        errors.append(f"{prov['name']}: HTTP {resp.status_code}")
                        continue
                    data = resp.json()
                    raw = data.get("data", [])
                    for m in raw:
                        mid = m.get("id", "unknown")
                        all_models.append({"id": mid, "provider": prov["name"]})
                    total_new += len(raw)
                    self.root.after(0, lambda n=prov["name"], c=len(raw): self.log(f"  ✅ {n}: {c} 个模型"))
                except Exception as e:
                    errors.append(f"{prov['name']}: {e}")

            # 去重
            seen = set()
            deduped = []
            for m in all_models:
                key = (m["id"], m["provider"])
                if key not in seen:
                    seen.add(key)
                    deduped.append(m)

            self.models = deduped
            self.models.sort(key=lambda x: (x["provider"], x["id"]))

            self.selected_models = {m["id"] for m in self.models if m["id"] in self.selected_models}

            self.root.after(0, self.refresh_model_tree)
            self.root.after(0, self.refresh_prov_tree)
            self.root.after(0, lambda: self.log(f"\n📥 拉取完成: 共 {total_new} 个新模型（去重后 {len(deduped)}）"))
            for e in errors:
                self.root.after(0, lambda err=e: self.log(f"  ❌ {err}", level="error"))
            self.root.after(0, lambda: self.set_status("就绪"))
            self.root.after(0, lambda: self.fetch_btn.configure(state=tk.NORMAL))
            self.root.after(0, lambda: self.set_buttons_fetching(False))

        threading.Thread(target=do_fetch_all, daemon=True).start()

    def set_buttons_fetching(self, fetching):
        state = tk.DISABLED if fetching else tk.NORMAL
        self.fetch_btn.configure(state=state)

    # ──────────────── 交互逻辑 ────────────────

    def log(self, msg, level="info"):
        self.result_text.configure(state=tk.NORMAL)
        ts = datetime.now().strftime("%H:%M:%S")
        tag_map = {"success": "success_tag", "error": "error_tag"}
        tag = tag_map.get(level)
        line = f"[{ts}] {msg}\n"
        self.result_text.insert(tk.END, line, tag)
        self.result_text.see(tk.END)
        self.result_text.configure(state=tk.DISABLED)

        if level == "success":
            self.status_bar.configure(foreground=self.colors["success"])
        elif level == "error":
            self.status_bar.configure(foreground=self.colors["error"])
        else:
            self.status_bar.configure(foreground=self.colors["fg"])
        self.status_bar.configure(text=msg)
        self.root.update_idletasks()

    def set_status(self, text):
        self.status_bar.configure(text=text, foreground=self.colors["fg"])
        self.root.update_idletasks()

    def request_stop(self):
        self.stop_testing = True
        self.log("⏹ 正在停止测试...", level="error")

    # ──────────────── 测试逻辑 ────────────────

    def test_selected(self):
        if not self.selected_models:
            messagebox.showinfo("提示", "请先勾选要测试的模型")
            return
        self.run_tests(list(self.selected_models))

    def test_all(self):
        if not self.models:
            return
        self.run_tests([m["id"] for m in self.models])

    def run_tests(self, model_id_list):
        if not model_id_list:
            return

        # 构建 model_id → provider 映射
        model_prov_map = {}
        for m in self.models:
            if m["id"] in model_id_list:
                model_prov_map[m["id"]] = m["provider"]

        if not model_prov_map:
            messagebox.showwarning("提示", "未找到对应的模型信息")
            return

        prompt = self.prompt_var.get().strip() or "你好"

        self.testing = True
        self.stop_testing = False
        self.set_buttons_testing(True)

        total = len(model_id_list)
        self.log(f"\n{'='*60}")
        self.log(f"🚀 开始并发测试 {total} 个模型，Prompt: 「{prompt}」")

        max_workers = min(total, 6)  # 最多 6 个并发
        self.log(f"⚡ 并发数: {max_workers}")

        completed = [0]
        c_lock = threading.Lock()

        def test_one(model_id):
            """单个模型测试（在工作线程中执行）"""
            if self.stop_testing:
                return

            provider_name = model_prov_map.get(model_id, "")
            prov_url = ""
            prov_key = ""
            for p in self.providers:
                if p["name"] == provider_name:
                    prov_url = p["url"]
                    prov_key = p["key"]
                    break

            if not prov_url or not prov_key:
                self.root.after(0, lambda m=model_id: self.update_model_status(m, "skip"))
                self.root.after(0, lambda m=model_id: self.log(f"  ⚠ {m}: 找不到提供商信息", level="error"))
                with c_lock:
                    completed[0] += 1
                return

            self.root.after(0, lambda m=model_id: self.update_model_status(m, "testing"))
            self.root.after(0, lambda m=model_id, p=provider_name: self.log(f"🔍 {m} @{p}"))

            ok, latency, reply = self.test_single_model(prov_url, prov_key, model_id, prompt)
            self.root.after(0, lambda m=model_id, s="ok" if ok else "fail": self.update_model_status(m, s))

            if ok:
                self.root.after(0, lambda m=model_id, l=latency: self.log(
                    f"  ✅ {m} — {l:.1f}s", level="success"))
                self.root.after(0, lambda r=reply: self.log(
                    f"     回复: {r[:200]}"))
            else:
                self.root.after(0, lambda m=model_id, l=latency: self.log(
                    f"  ❌ {m} — {l}", level="error"))

            with c_lock:
                completed[0] += 1
                done = completed[0]
            self.root.after(0, lambda d=done, t=total: self.set_status(f"测试进度: {d}/{t}"))

            if done >= total:
                self.root.after(300, self.finish_tests)

        def worker():
            """在后台线程中管理线程池"""
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
                futs = [pool.submit(test_one, mid) for mid in model_id_list]
                # 等所有任务完成或被停止
                for fut in concurrent.futures.as_completed(futs):
                    if self.stop_testing:
                        # 取消剩余任务
                        for f in futs:
                            f.cancel()
                        pool.shutdown(wait=False, cancel_futures=True)
                        self.root.after(0, lambda: self.log("⏹ 测试已停止", level="error"))
                        self.root.after(300, self.finish_tests)
                        return

        threading.Thread(target=worker, daemon=True).start()

    def test_single_model(self, base_url, api_key, model_name, prompt):
        payload = {
            "model": model_name,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 100,
            "temperature": 0.7,
            "stream": False,
        }
        start = time.time()
        try:
            resp = requests.post(
                f"{base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=60,
            )
            elapsed = time.time() - start
            if resp.status_code == 200:
                data = resp.json()
                choices = data.get("choices", [])
                if choices:
                    msg = choices[0].get("message", {})
                    content = msg.get("content", "").strip()
                    return True, elapsed, content
                return False, f"{elapsed:.1f}s (空回复)", ""
            body = resp.text[:200]
            return False, f"HTTP {resp.status_code}", body
        except requests.Timeout:
            return False, f"{time.time()-start:.1f}s (超时)", ""
        except Exception as e:
            return False, f"异常: {e}", ""

    def update_model_status(self, model_id, status):
        if self.model_tree.exists(model_id):
            status_map = {
                "testing": "⏳ 测试中...",
                "ok":       "✅ 正常",
                "fail":     "❌ 失败",
                "skip":     "⚠ 跳过",
            }
            self.model_tree.set(model_id, "status", status_map.get(status, ""))
        self.root.update_idletasks()
        self._update_test_stats()

    def _update_test_stats(self):
        """更新成功/失败统计显示"""
        total = 0
        passed = 0
        failed = 0
        for item in self.model_tree.get_children():
            st = self.model_tree.set(item, "status")
            if st:
                total += 1
                if "正常" in st:
                    passed += 1
                elif "失败" in st:
                    failed += 1
        self.pass_count_label.configure(text=f"✅成功 {passed}" if passed else "")
        self.fail_count_label.configure(text=f"❌失败 {failed}" if failed else "")
        self.root.update_idletasks()

    def set_buttons_testing(self, testing):
        state = tk.DISABLED if testing else tk.NORMAL
        self.fetch_btn.configure(state=state)
        self.test_selected_btn.configure(state=state)
        self.test_all_btn.configure(state=state)
        self.stop_btn.configure(state=tk.NORMAL if testing else tk.DISABLED)
        self.model_select_all_cb.configure(state=state if self.models else tk.DISABLED)
        self.root.update_idletasks()

    def finish_tests(self):
        self.testing = False
        self.set_buttons_testing(False)
        self.set_status("测试完成")
        total = 0
        passed = 0
        for item in self.model_tree.get_children():
            st = self.model_tree.set(item, "status")
            if st:
                total += 1
                if "正常" in st:
                    passed += 1
        self.log(f"\n📊 汇总: 通过 {passed}/{total}")
        self.log(f"{'='*60}\n")

    def on_close(self):
        self.save_providers()  # 关闭前保存
        if self.testing:
            if not messagebox.askyesno("确认", "测试正在进行中，确定退出？"):
                return
            self.stop_testing = True
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = ModelTesterApp(root)
    root.mainloop()
