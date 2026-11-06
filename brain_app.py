import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import threading
import time
import urllib.request
from typing import Any, Callable, Dict, List, Optional

CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from db_engine import BrainDB, ensure_dashboard_running
from orbit_engine import OrbitEngine

APP_TITLE = "Antigravity Brain v5.0 — Neural OS & Prompt Forge"
DASHBOARD_URL = "http://127.0.0.1:8765"
ICON_ICO_PATH = CURRENT_DIR / "brain_app.ico"
ICON_PNG_PATH = CURRENT_DIR / "brain_app.png"


# =============================================================================
# 1. GERADOR AUTOMÁTICO DE ÍCONE CYBERPUNK (.ICO & .PNG) — 0 ASSETS EXTERNOS
# =============================================================================
def ensure_app_icons() -> Dict[str, str]:
    """
    Gera automaticamente os ícones oficiais brain_app.ico (multi-resolução) e brain_app.png
    com estética Cyberpunk Neural (roxo/ciano/esmeralda sobre safira escuro).
    Usa Pillow se disponível ou gerador binário ICO/BMP nativo como fallback.
    """
    if ICON_ICO_PATH.is_file() and ICON_PNG_PATH.is_file() and ICON_ICO_PATH.stat().st_size > 1024:
        return {"ico": str(ICON_ICO_PATH), "png": str(ICON_PNG_PATH)}

    try:
        from PIL import Image, ImageDraw

        size = 256
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Fundo arredondado escuro (#070a14) com borda néon dupla
        draw.rounded_rectangle((8, 8, 248, 248), radius=54, fill=(7, 10, 20, 255), outline=(99, 102, 241, 255), width=6)
        draw.rounded_rectangle((18, 18, 238, 238), radius=46, fill=(11, 16, 32, 255), outline=(168, 85, 247, 180), width=3)

        # Anel orbital exterior
        draw.ellipse((38, 38, 218, 218), outline=(56, 189, 248, 130), width=4)
        draw.ellipse((58, 58, 198, 198), outline=(168, 85, 247, 180), width=4)

        # Ligações sinápticas (Grafo Neural)
        nodes = [
            (128, 52, (56, 189, 248, 255)),   # Topo (Ciano)
            (194, 90, (168, 85, 247, 255)),   # Direita-Topo (Roxo)
            (194, 166, (16, 185, 129, 255)),  # Direita-Baixo (Esmeralda)
            (128, 204, (99, 102, 241, 255)),  # Baixo (Indigo)
            (62, 166, (16, 185, 129, 255)),   # Esquerda-Baixo (Esmeralda)
            (62, 90, (168, 85, 247, 255)),    # Esquerda-Topo (Roxo)
            (128, 128, (248, 250, 252, 255)), # Núcleo Central (Branco/Néon)
        ]
        center = (128, 128)
        for nx, ny, _ in nodes[:-1]:
            draw.line((center[0], center[1], nx, ny), fill=(139, 92, 246, 220), width=6)

        for i in range(6):
            x1, y1, _ = nodes[i]
            x2, y2, _ = nodes[(i + 1) % 6]
            draw.line((x1, y1, x2, y2), fill=(56, 189, 248, 190), width=4)

        # Desenhar nós sinápticos
        for nx, ny, col in nodes[:-1]:
            r = 15
            draw.ellipse((nx - r - 4, ny - r - 4, nx + r + 4, ny + r + 4), fill=(col[0], col[1], col[2], 95))
            draw.ellipse((nx - r, ny - r, nx + r, ny + r), fill=col, outline=(255, 255, 255, 230), width=3)

        # Núcleo Central (Brain Core)
        cr = 26
        draw.ellipse((128 - cr - 8, 128 - cr - 8, 128 + cr + 8, 128 + cr + 8), fill=(168, 85, 247, 130))
        draw.ellipse((128 - cr, 128 - cr, 128 + cr, 128 + cr), fill=(99, 102, 241, 255), outline=(110, 231, 183, 255), width=5)
        draw.ellipse((128 - 10, 128 - 10, 128 + 10, 128 + 10), fill=(255, 255, 255, 255))

        img.save(str(ICON_PNG_PATH), format="PNG")
        img.save(
            str(ICON_ICO_PATH),
            format="ICO",
            sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
        )
        return {"ico": str(ICON_ICO_PATH), "png": str(ICON_PNG_PATH)}
    except Exception:
        # Fallback binário ICO 32x32 32-bit BGRA sem dependências externas
        w, h = 32, 32
        pixels = bytearray(w * h * 4)
        for y in range(h):
            for x in range(w):
                idx = (y * w + x) * 4
                dx, dy = x - 15.5, y - 15.5
                dist = (dx * dx + dy * dy) ** 0.5
                if dist < 5.0:
                    pixels[idx : idx + 4] = bytes((255, 230, 110, 255))  # Núcleo Ciano/Branco
                elif dist < 12.5:
                    pixels[idx : idx + 4] = bytes((241, 102, 99, 255))   # Anel Indigo/Roxo
                elif dist < 15.0:
                    pixels[idx : idx + 4] = bytes((24, 14, 9, 255))      # Borda Escura
                else:
                    pixels[idx : idx + 4] = bytes((0, 0, 0, 0))
        and_mask = bytes((w // 8) * h)
        bmp_header = struct.pack("<IIIHHIIIIII", 40, w, h * 2, 1, 32, 0, len(pixels) + len(and_mask), 0, 0, 0, 0)
        ico_data = bmp_header + bytes(pixels) + and_mask
        ico_dir = struct.pack("<HHH", 0, 1, 1) + struct.pack("<BBBBHHII", w, h, 0, 0, 1, 32, len(ico_data), 22)
        ICON_ICO_PATH.write_bytes(ico_dir + ico_data)
        return {"ico": str(ICON_ICO_PATH), "png": str(ICON_PNG_PATH)}


# =============================================================================
# 2. LANÇADOR DE JANELA NATIVA (--app CHROMELESS EDGE/CHROME WEBVIEW)
# =============================================================================
def find_native_app_browser() -> Optional[str]:
    """Localiza o motor Edge WebView / Chrome instalado no Windows para abrir janela --app nativa."""
    candidates = [
        os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%LocalAppData%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%ProgramFiles%\BraveSoftware\Brave-Browser\Application\brave.exe"),
    ]
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    return None


def launch_native_app_window(section: str = "graph") -> Dict[str, Any]:
    """
    Garante que o daemon web_dashboard.py está ativo e abre o Antigravity Brain
    numa janela de aplicação dedicada (--app, sem barra de endereço nem separadores).
    """
    ensure_app_icons()
    ensure_dashboard_running(force_restart=False)

    clean_sec = (section or "graph").strip().lstrip("#").lower()
    target_url = f"{DASHBOARD_URL}/?app=1#{clean_sec}"

    browser_exe = find_native_app_browser()
    if browser_exe:
        profile_dir = CURRENT_DIR / ".brain_app_profile"
        profile_dir.mkdir(parents=True, exist_ok=True)
        cmd = [
            browser_exe,
            f"--app={target_url}",
            "--window-size=1520,940",
            f"--user-data-dir={profile_dir}",
            "--no-first-run",
            "--no-default-browser-check",
        ]
        creation_flags = 0x08000000 if os.name == "nt" else 0
        subprocess.Popen(
            cmd,
            cwd=str(CURRENT_DIR),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creation_flags,
        )
        return {"ok": True, "mode": "native_app_window", "browser": browser_exe, "url": target_url}

    import webbrowser

    webbrowser.open(target_url)
    return {"ok": True, "mode": "browser_fallback", "url": target_url}


# =============================================================================
# 3. CRIAÇÃO DE ATALHOS NATIVOS (.LNK) NO AMBIENTE DE TRABALHO & MENU INICIAR
# =============================================================================
def ensure_desktop_shortcuts() -> Dict[str, Any]:
    """
    Cria o atalho nativo 'Antigravity Brain.lnk' no Ambiente de Trabalho (Desktop)
    e no Menu Iniciar do Windows com o ícone Cyberpunk brain_app.ico.
    """
    icons = ensure_app_icons()
    if os.name != "nt":
        return {"ok": False, "reason": "non-windows"}

    pythonw_exe = Path(sys.executable).resolve().parent / "pythonw.exe"
    if not pythonw_exe.is_file():
        pythonw_exe = Path(sys.executable).resolve()

    app_script = str(CURRENT_DIR / "brain_app.py")
    ico_path = icons["ico"]

    ps_script = f"""
$WshShell = New-Object -ComObject WScript.Shell
$DesktopDir = [Environment]::GetFolderPath('Desktop')
$StartMenuDir = [Environment]::GetFolderPath('Programs')

foreach ($TargetDir in @($DesktopDir, $StartMenuDir)) {{
    if ($TargetDir -and (Test-Path $TargetDir)) {{
        $ShortcutPath = Join-Path $TargetDir 'Antigravity Brain.lnk'
        $Shortcut = $WshShell.CreateShortcut($ShortcutPath)
        $Shortcut.TargetPath = '{pythonw_exe}'
        $Shortcut.Arguments = '"{app_script}" --open-app'
        $Shortcut.WorkingDirectory = '{CURRENT_DIR}'
        $Shortcut.IconLocation = '{ico_path},0'
        $Shortcut.Description = 'Antigravity Brain v5.0 — Neural OS, Self-Learn Studio & Prompt Forge (Ctrl+Shift+B)'
        $Shortcut.Save()
    }}
}}
"""
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-Command", ps_script],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=8,
            creationflags=0x08000000,
        )
        desktop_lnk = Path(os.path.expanduser("~/Desktop")) / "Antigravity Brain.lnk"
        return {
            "ok": True,
            "desktop_shortcut": str(desktop_lnk),
            "icon": ico_path,
            "target": f'"{pythonw_exe}" "{app_script}" --open-app',
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


# =============================================================================
# 4. SPOTLIGHT QUICK PROMPT FORGE (JANELA FLUTUANTE DARK CYBERPUNK — CTRL+SHIFT+B)
# =============================================================================
class QuickPromptForgeSpotlight:
    """
    Janela flutuante estilo Raycast/Spotlight ('Always on Top') invocável em qualquer lugar
    com Ctrl+Shift+B ou a partir do System Tray para gerar e copiar Super-Prompts em 2 segundos.
    """

    TASK_MODES = [
        ("feature", "🚀 Nova Funcionalidade (Feature)"),
        ("bugfix", "🐛 Correção de Bug & Root-Cause"),
        ("total_audit", "🔍 Auditoria Total 360° (5 Eixos + Matriz + Auto-Fix)"),
        ("refactor", "♻️ Refatoração & Clean Code"),
        ("performance", "⚡ Otimização de Performance & 60 FPS"),
        ("ui_ux", "🎨 UI/UX & Design Visual Interativo"),
        ("security", "🛡️ Auditoria de Segurança & Hardening"),
        ("architecture", "🏛️ Arquitetura / Ultraplan Multi-Fase"),
    ]

    def __init__(self) -> None:
        self.root: Any = None
        self._lock = threading.Lock()
        self._last_prompt_text: str = ""

    def show_or_focus(self, initial_mode: Optional[str] = None) -> None:
        if self.root is not None:
            try:
                self.root.after(0, lambda: self._PopupExisting(initial_mode))
                return
            except Exception:
                self.root = None

        threading.Thread(target=self._run_tk_window, args=(initial_mode,), daemon=True).start()

    def _PopupExisting(self, initial_mode: Optional[str] = None) -> None:
        if not self.root:
            return
        self.root.deiconify()
        self.root.lift()
        self.root.attributes("-topmost", True)
        self.root.focus_force()
        if initial_mode and hasattr(self, "mode_var"):
            for code, label in self.TASK_MODES:
                if code == initial_mode:
                    self.mode_var.set(label)
                    break
        if hasattr(self, "entry_req"):
            self.entry_req.focus_set()

    def _run_tk_window(self, initial_mode: Optional[str] = None) -> None:
        try:
            import tkinter as tk
            from tkinter import ttk

            ensure_app_icons()
            db = BrainDB()
            orb = OrbitEngine(db)
            sl_status = orb.get_self_learn_status("brain_mcp")
            projects = [p["workspace"] for p in sl_status.get("projects", []) if p.get("workspace")]
            if not projects:
                projects = ["brain_mcp"]

            root = tk.Tk()
            self.root = root
            root.title("⚡ Antigravity Brain — Quick Prompt Forge Spotlight (Ctrl+Shift+B)")
            root.configure(bg="#070a14")
            root.attributes("-topmost", True)
            if ICON_ICO_PATH.is_file():
                try:
                    root.iconbitmap(str(ICON_ICO_PATH))
                except Exception:
                    pass

            w, h = 820, 560
            sw = root.winfo_screenwidth()
            sh = root.winfo_screenheight()
            x = max(20, (sw - w) // 2)
            y = max(20, (sh - h) // 3)
            root.geometry(f"{w}x{h}+{x}+{y}")

            # Estilo Dark Cyberpunk
            style = ttk.Style(root)
            try:
                style.theme_use("clam")
            except Exception:
                pass
            style.configure(
                "TCombobox",
                fieldbackground="#0f172a",
                background="#1e293b",
                foreground="#f8fafc",
                arrowcolor="#a855f7",
            )

            # Header
            hdr = tk.Frame(root, bg="#0d1326", highlightbackground="#4f46e5", highlightthickness=1)
            hdr.pack(fill="x", padx=12, pady=(12, 8))

            tk.Label(
                hdr,
                text="✨ ANTIGRAVITY BRAIN — QUICK PROMPT FORGE SPOTLIGHT",
                font=("Consolas", 11, "bold"),
                fg="#c084fc",
                bg="#0d1326",
            ).pack(side="left", padx=10, pady=8)

            tk.Label(
                hdr,
                text="Atalho Global: Ctrl+Shift+B · Enter = Forjar & Copiar",
                font=("Consolas", 9),
                fg="#6ee7b7",
                bg="#0d1326",
            ).pack(side="right", padx=10, pady=8)

            # Barra de Navegação Rápida para abrir a App Desktop completa
            nav_bar = tk.Frame(root, bg="#070a14")
            nav_bar.pack(fill="x", padx=12, pady=(0, 8))

            nav_buttons = [
                ("🖥️ Abrir App Completa", "graph", "#6366f1"),
                ("✨ Estúdio Prompt Forge", "promptforge", "#a855f7"),
                ("🧬 Self-Learn Studio", "selflearn", "#10b981"),
                ("🏢 Escritório 3D", "office", "#38bdf8"),
                ("🛰️ Orbit OS", "orbit", "#f59e0b"),
            ]
            for lbl, sec, col in nav_buttons:
                btn = tk.Button(
                    nav_bar,
                    text=lbl,
                    font=("Segoe UI", 8, "bold"),
                    fg="#f8fafc",
                    bg="#111827",
                    activebackground="#1e293b",
                    activeforeground="#ffffff",
                    relief="flat",
                    bd=1,
                    padx=8,
                    pady=4,
                    cursor="hand2",
                    command=lambda s=sec: launch_native_app_window(s),
                )
                btn.pack(side="left", padx=(0, 6))

            # Seletores de Projeto e Modo de Engenharia
            ctrl_row = tk.Frame(root, bg="#070a14")
            ctrl_row.pack(fill="x", padx=12, pady=(0, 8))

            tk.Label(ctrl_row, text="📂 Projeto:", font=("Consolas", 9, "bold"), fg="#94a3b8", bg="#070a14").pack(
                side="left", padx=(0, 6)
            )
            self.ws_var = tk.StringVar(value="brain_mcp" if "brain_mcp" in projects else projects[0])
            ws_cb = ttk.Combobox(ctrl_row, textvariable=self.ws_var, values=projects, width=22, state="readonly")
            ws_cb.pack(side="left", padx=(0, 14))

            tk.Label(ctrl_row, text="🎯 Missão:", font=("Consolas", 9, "bold"), fg="#94a3b8", bg="#070a14").pack(
                side="left", padx=(0, 6)
            )
            mode_labels = [lbl for _, lbl in self.TASK_MODES]
            default_mode_lbl = mode_labels[0]
            if initial_mode:
                for c, l in self.TASK_MODES:
                    if c == initial_mode:
                        default_mode_lbl = l
                        break
            self.mode_var = tk.StringVar(value=default_mode_lbl)
            mode_cb = ttk.Combobox(ctrl_row, textvariable=self.mode_var, values=mode_labels, width=42, state="readonly")
            mode_cb.pack(side="left", fill="x", expand=True)

            # Input do Pedido Rápido
            inp_frame = tk.Frame(root, bg="#0f172a", highlightbackground="#a855f7", highlightthickness=1)
            inp_frame.pack(fill="x", padx=12, pady=(0, 8))

            self.entry_req = tk.Entry(
                inp_frame,
                font=("Segoe UI", 11),
                fg="#f8fafc",
                bg="#0f172a",
                insertbackground="#c084fc",
                relief="flat",
            )
            self.entry_req.pack(side="left", fill="x", expand=True, padx=10, pady=10)
            self.entry_req.insert(0, "Faz uma auditoria total 360 ao projeto e corrige os bugs críticos")
            self.entry_req.select_range(0, "end")

            status_var = tk.StringVar(
                value="💡 Escreve o teu pedido em 1 linha e carrega em Enter para gerar e copiar o Super-Prompt!"
            )

            output_box = tk.Text(
                root,
                font=("Consolas", 9),
                fg="#e2e8f0",
                bg="#090d18",
                insertbackground="#38bdf8",
                relief="flat",
                wrap="word",
                height=16,
            )

            def _do_forge(*_args: Any) -> None:
                req_txt = self.entry_req.get().strip()
                ws_val = self.ws_var.get().strip() or "brain_mcp"
                sel_lbl = self.mode_var.get()
                mode_code = "feature"
                for c, l in self.TASK_MODES:
                    if l == sel_lbl:
                        mode_code = c
                        break
                if not req_txt and mode_code == "total_audit":
                    req_txt = f"Executa uma Auditoria Total 360° (5 Eixos) ao projeto {ws_val} e corrige os problemas críticos"
                elif not req_txt:
                    status_var.set("⚠️ Escreve primeiro uma breve descrição do que queres fazer.")
                    return

                res = orb.generate_optimized_prompt(
                    raw_request=req_txt,
                    workspace=ws_val,
                    task_mode=mode_code,
                )
                prompt_str = str(res.get("optimized_prompt") or "")
                self._last_prompt_text = prompt_str

                output_box.delete("1.0", "end")
                output_box.insert("1.0", prompt_str)

                root.clipboard_clear()
                root.clipboard_append(prompt_str)
                root.update()

                sk_cnt = len(res.get("matched_skills") or [])
                fl_cnt = len(res.get("matched_files") or [])
                tok_est = res.get("token_estimate") or 0
                status_var.set(
                    f"✅ COPIADO PARA O CLIPBOARD! ({tok_est} tokens · {sk_cnt} Skills Antigravity · {fl_cnt} Ficheiros) — Faz Ctrl+V no Antigravity!"
                )

            forge_btn = tk.Button(
                inp_frame,
                text="⚡ FORJAR & COPIAR",
                font=("Consolas", 10, "bold"),
                fg="#ffffff",
                bg="#7c3aed",
                activebackground="#6d28d9",
                activeforeground="#ffffff",
                relief="flat",
                padx=14,
                pady=8,
                cursor="hand2",
                command=_do_forge,
            )
            forge_btn.pack(side="right", padx=6, pady=6)

            self.entry_req.bind("<Return>", _do_forge)
            root.bind("<Escape>", lambda _e: root.withdraw())

            # Barra de Status
            st_lbl = tk.Label(
                root,
                textvariable=status_var,
                font=("Consolas", 9, "bold"),
                fg="#6ee7b7",
                bg="#070a14",
                anchor="w",
            )
            st_lbl.pack(fill="x", padx=14, pady=(0, 4))

            # Output Preview
            out_frame = tk.Frame(root, bg="#090d18", highlightbackground="#1e293b", highlightthickness=1)
            out_frame.pack(fill="both", expand=True, padx=12, pady=(0, 12))
            output_box.pack(fill="both", expand=True, padx=8, pady=8)

            self.entry_req.focus_set()
            if initial_mode == "total_audit":
                root.after(120, _do_forge)

            root.protocol("WM_DELETE_WINDOW", root.withdraw)
            root.mainloop()
        except Exception:
            self.root = None


# =============================================================================
# 5. WINDOWS SYSTEM TRAY NATIVO (SHELL_NOTIFYICONW) + GLOBAL HOTKEY (CTRL+SHIFT+B)
# =============================================================================
WM_USER = 0x0400
WM_TRAYICON = WM_USER + 20
WM_COMMAND = 0x0111
WM_DESTROY = 0x0002
WM_HOTKEY = 0x0312
WM_LBUTTONDBLCLK = 0x0203
WM_LBUTTONUP = 0x0202
WM_RBUTTONUP = 0x0205

NIM_ADD = 0x00000000
NIM_MODIFY = 0x00000001
NIM_DELETE = 0x00000002
NIF_MESSAGE = 0x00000001
NIF_ICON = 0x00000002
NIF_TIP = 0x00000004

IMAGE_ICON = 1
LR_LOADFROMFILE = 0x00000010
LR_DEFAULTSIZE = 0x00000040

TPM_LEFTALIGN = 0x0000
TPM_RETURNCMD = 0x0100
TPM_NONOTIFY = 0x0080
MF_STRING = 0x00000000
MF_SEPARATOR = 0x00000800

MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_NOREPEAT = 0x4000
VK_B = 0x42
HOTKEY_ID_SPOTLIGHT = 9001


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT),
        ("hIcon", wintypes.HICON),
        ("szTip", wintypes.WCHAR * 128),
        ("dwState", wintypes.DWORD),
        ("dwStateMask", wintypes.DWORD),
        ("szInfo", wintypes.WCHAR * 256),
        ("uTimeoutOrVersion", wintypes.UINT),
        ("szInfoTitle", wintypes.WCHAR * 64),
        ("dwInfoFlags", wintypes.DWORD),
    ]


WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)


class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]


class BrainSystemTrayAgent:
    """
    Agente nativo na Bandeja do Sistema (System Tray) do Windows + Atalho Global Ctrl+Shift+B.
    Funciona em 100% dos PCs Windows sem bibliotecas externas (puro Win32 ctypes).
    """

    ID_OPEN_APP = 1001
    ID_OPEN_SPOTLIGHT = 1002
    ID_OPEN_PROMPT_FORGE = 1003
    ID_OPEN_SELF_LEARN = 1004
    ID_RUN_TOTAL_AUDIT = 1005
    ID_EVOLVE_ALL = 1006
    ID_CREATE_SHORTCUT = 1007
    ID_EXIT = 1099

    def __init__(self, open_window_on_start: bool = True) -> None:
        self.open_window_on_start = open_window_on_start
        self.spotlight = QuickPromptForgeSpotlight()
        self.hwnd: Optional[int] = None
        self.nid: Optional[NOTIFYICONDATAW] = None
        self._wndproc_ref: Optional[Any] = None

    def _trigger_evolve_all_bg(self) -> None:
        def _worker() -> None:
            try:
                orb = OrbitEngine(BrainDB())
                orb.enable_and_evolve_all_projects("brain_mcp")
            except Exception:
                pass

        threading.Thread(target=_worker, daemon=True).start()

    def _show_context_menu(self, hwnd: int) -> None:
        user32 = ctypes.windll.user32
        hmenu = user32.CreatePopupMenu()
        items = [
            (self.ID_OPEN_APP, "🖥️ Abrir Antigravity Brain (App Desktop)"),
            (self.ID_OPEN_SPOTLIGHT, "⚡ Quick Prompt Forge Spotlight (Ctrl+Shift+B)"),
            (0, None),
            (self.ID_OPEN_PROMPT_FORGE, "✨ Abrir Estúdio Prompt Forge Completo"),
            (self.ID_OPEN_SELF_LEARN, "🧬 Abrir Self-Learn Studio (Pipeline 60 FPS)"),
            (self.ID_RUN_TOTAL_AUDIT, "🔍 Gerar Super-Prompt de Auditoria Total 360°"),
            (self.ID_EVOLVE_ALL, "🟢 Evoluir Todos os Projetos Agora (Self-Learn)"),
            (0, None),
            (self.ID_CREATE_SHORTCUT, "📌 Recriar Atalho no Ambiente de Trabalho"),
            (self.ID_EXIT, "❌ Encerrar Ícone da Bandeja (Tray)"),
        ]
        for cmd_id, label in items:
            if label is None:
                user32.AppendMenuW(hmenu, MF_SEPARATOR, 0, None)
            else:
                user32.AppendMenuW(hmenu, MF_STRING, cmd_id, label)

        pt = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        user32.SetForegroundWindow(hwnd)
        cmd = user32.TrackPopupMenu(
            hmenu,
            TPM_LEFTALIGN | TPM_RETURNCMD | TPM_NONOTIFY,
            pt.x,
            pt.y,
            0,
            hwnd,
            None,
        )
        user32.DestroyMenu(hmenu)

        if cmd == self.ID_OPEN_APP:
            launch_native_app_window("graph")
        elif cmd == self.ID_OPEN_SPOTLIGHT:
            self.spotlight.show_or_focus()
        elif cmd == self.ID_OPEN_PROMPT_FORGE:
            launch_native_app_window("promptforge")
        elif cmd == self.ID_OPEN_SELF_LEARN:
            launch_native_app_window("selflearn")
        elif cmd == self.ID_RUN_TOTAL_AUDIT:
            self.spotlight.show_or_focus(initial_mode="total_audit")
        elif cmd == self.ID_EVOLVE_ALL:
            self._trigger_evolve_all_bg()
            launch_native_app_window("selflearn")
        elif cmd == self.ID_CREATE_SHORTCUT:
            ensure_desktop_shortcuts()
        elif cmd == self.ID_EXIT:
            self.stop()

    def stop(self) -> None:
        if self.nid is not None:
            ctypes.windll.shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self.nid))
            self.nid = None
        if self.hwnd:
            ctypes.windll.user32.UnregisterHotKey(self.hwnd, HOTKEY_ID_SPOTLIGHT)
            ctypes.windll.user32.PostQuitMessage(0)

    def run(self) -> None:
        if os.name != "nt":
            launch_native_app_window("graph")
            return

        ensure_app_icons()
        ensure_desktop_shortcuts()
        ensure_dashboard_running(force_restart=False)

        if self.open_window_on_start:
            launch_native_app_window("graph")

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        shell32 = ctypes.windll.shell32

        # Garantir uma única instância do Tray Agent
        mutex = kernel32.CreateMutexW(None, False, "Global\\AntigravityBrainTrayMutex_v5")
        if kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
            return

        def _wnd_proc(hwnd: int, msg: int, wparam: int, lparam: int) -> int:
            if msg == WM_TRAYICON:
                if lparam == WM_LBUTTONDBLCLK:
                    launch_native_app_window("graph")
                elif lparam == WM_LBUTTONUP:
                    self.spotlight.show_or_focus()
                elif lparam == WM_RBUTTONUP:
                    self._show_context_menu(hwnd)
                return 0
            if msg == WM_HOTKEY and wparam == HOTKEY_ID_SPOTLIGHT:
                self.spotlight.show_or_focus()
                return 0
            if msg == WM_DESTROY:
                self.stop()
                return 0
            return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

        self._wndproc_ref = WNDPROC(_wnd_proc)
        hinst = kernel32.GetModuleHandleW(None)
        class_name = "AntigravityBrainTrayWndClass"

        wc = WNDCLASSW()
        wc.lpfnWndProc = self._wndproc_ref
        wc.hInstance = hinst
        wc.lpszClassName = class_name
        user32.RegisterClassW(ctypes.byref(wc))

        hwnd = user32.CreateWindowExW(
            0, class_name, "AntigravityBrainTrayWindow", 0, 0, 0, 0, 0, None, None, hinst, None
        )
        self.hwnd = hwnd

        hicon = user32.LoadImageW(
            None, str(ICON_ICO_PATH), IMAGE_ICON, 0, 0, LR_LOADFROMFILE | LR_DEFAULTSIZE
        )

        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = hwnd
        nid.uID = 1
        nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        nid.uCallbackMessage = WM_TRAYICON
        nid.hIcon = hicon
        nid.szTip = "Antigravity Brain v5.0 · Clique=Spotlight (Ctrl+Shift+B) · Duplo Clique=App"
        self.nid = nid
        shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid))

        # Registar Atalho Global Ctrl+Shift+B
        user32.RegisterHotKey(hwnd, HOTKEY_ID_SPOTLIGHT, MOD_CONTROL | MOD_SHIFT | MOD_NOREPEAT, VK_B)

        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

        if mutex:
            kernel32.CloseHandle(mutex)


def main() -> None:
    args = [a.lower() for a in sys.argv[1:]]
    if "--generate-icons" in args:
        res = ensure_app_icons()
        print(json.dumps(res))
        return
    if "--install-shortcut" in args:
        res = ensure_desktop_shortcuts()
        print(json.dumps(res))
        return
    if "--test-headless" in args:
        icons = ensure_app_icons()
        sc = ensure_desktop_shortcuts()
        browser = find_native_app_browser()
        print(
            json.dumps(
                {
                    "ok": os.path.isfile(icons["ico"]),
                    "icons": icons,
                    "shortcut": sc,
                    "native_browser": browser,
                }
            )
        )
        return
    if "--spotlight" in args:
        sp = QuickPromptForgeSpotlight()
        sp._run_tk_window(initial_mode="total_audit" if "--audit" in args else None)
        return

    open_win = "--tray-only" not in args
    agent = BrainSystemTrayAgent(open_window_on_start=open_win)
    agent.run()


if __name__ == "__main__":
    main()
