from __future__ import annotations

"""
Tema Neumorphism (Soft UI) centralizado para ttk.

Tkinter no dibuja sombras reales: el efecto se simula con tema "clam", relieves
raised/sunken y pares lightcolor/darkcolor. Toda la app debe usar QDV_COLORS y
apply_qdv_theme() para consistencia.
"""

from tkinter import ttk

# --- Paleta Neumorphism: base azul-gris suave + acentos vivos pero profesionales ---
QDV_COLORS = {
    # Superficies (contraste suave típico neu: base un poco más profunda que la tarjeta)
    "bg": "#D8E0ED",
    "card": "#E8EEF7",
    "card_elevated": "#EEF3FA",
    # Simulación de luz/sombra (bordes de relieve)
    "neu_light": "#FFFFFF",
    "neu_dark": "#A8B4C8",
    "neu_mid": "#BFC9D9",
    # Texto
    "fg": "#2D3748",
    "muted": "#64748B",
    "border": "#C5D0E0",
    # Acentos (más color, armonía fría + toques cálidos)
    "accent": "#5C7CFA",
    "accent_hover": "#4C6CE8",
    "accent_pressed": "#3D5AD4",
    "accent2": "#9B7EDE",
    "teal": "#2DB5A8",
    "coral": "#E9897A",
    "info": "#3D9BC9",
    "success": "#3DAB7A",
    "warning": "#D9A23C",
    "danger": "#E85D5D",
    # Estados de campos
    "warn_bg": "#F4E8C8",
    "error_bg": "#F0D8D8",
    "success_bg": "#D8F0E4",
    "input_bg": "#E8EEF7",
    "input_inset": "#D4DCE8",
    # Tablas
    "heading_bg": "#C8E8F0",
    "heading_fg": "#1A4A5C",
    "tree_sel_bg": "#B8D4F8",
    "tree_sel_fg": "#1E3A6E",
    "font_family": "Segoe UI",
}


def apply_qdv_theme(style: ttk.Style) -> None:
    """
    Aplica estilo Neumorphism global (relieves suaves, más color, botones táctiles).
    """
    c = QDV_COLORS

    try:
        style.theme_use("clam")
    except Exception:
        pass

    # Defaults
    try:
        style.configure(
            ".",
            background=c["bg"],
            foreground=c["fg"],
            font=(c["font_family"], 10),
        )
    except Exception:
        pass

    # Tarjetas / paneles elevados
    style.configure(
        "QDV.Card.TFrame",
        background=c["card"],
        relief="flat",
        borderwidth=0,
    )
    style.configure(
        "QDV.NeuPanel.TFrame",
        background=c["card_elevated"],
        relief="raised",
        borderwidth=2,
        lightcolor=c["neu_light"],
        darkcolor=c["neu_dark"],
    )
    style.configure("QDV.OnCard.TFrame", background=c["card_elevated"])
    # Columnas / zonas sobre tarjeta principal (ligero contraste neu)
    style.configure("QDV.CardInner.TFrame", background=c["card_elevated"])

    # Label frames: bloque “blando” con relieve
    style.configure(
        "TLabelframe",
        background=c["card"],
        foreground=c["fg"],
        bordercolor=c["neu_mid"],
        relief="raised",
        borderwidth=2,
        lightcolor=c["neu_light"],
        darkcolor=c["neu_dark"],
    )
    style.configure(
        "TLabelframe.Label",
        background=c["card"],
        foreground=c["accent"],
        font=(c["font_family"], 10, "bold"),
    )
    style.configure("TFrame", background=c["bg"])

    # Labels
    style.configure("TLabel", background=c["bg"], foreground=c["fg"])
    style.configure("QDV.Muted.TLabel", background=c["bg"], foreground=c["muted"])
    style.configure(
        "QDV.Title.TLabel",
        background=c["bg"],
        foreground=c["accent"],
        font=(c["font_family"], 19, "bold"),
    )
    # Títulos sobre tarjeta elevada (login, diálogos)
    style.configure(
        "QDV.TitleCard.TLabel",
        background=c["card_elevated"],
        foreground=c["accent"],
        font=(c["font_family"], 19, "bold"),
    )
    style.configure(
        "QDV.OnCard.TLabel",
        background=c["card_elevated"],
        foreground=c["fg"],
    )
    style.configure(
        "QDV.Section.TLabel",
        background=c["bg"],
        foreground=c["accent2"],
        font=(c["font_family"], 12, "bold"),
    )
    style.configure(
        "QDV.SectionCard.TLabel",
        background=c["card_elevated"],
        foreground=c["accent2"],
        font=(c["font_family"], 12, "bold"),
    )
    # Cabeceras sobre QDV.Card.TFrame
    style.configure(
        "QDV.HeaderTitle.TLabel",
        background=c["card"],
        foreground=c["accent2"],
        font=(c["font_family"], 18, "bold"),
    )
    style.configure(
        "QDV.HeaderSub.TLabel",
        background=c["card"],
        foreground=c["muted"],
        font=(c["font_family"], 11),
    )
    style.configure(
        "QDV.HeaderUser.TLabel",
        background=c["card"],
        foreground=c["teal"],
        font=(c["font_family"], 10, "bold"),
    )
    style.configure(
        "QDV.BodyCard.TLabel",
        background=c["card"],
        foreground=c["fg"],
        font=(c["font_family"], 11),
    )
    style.configure(
        "QDV.MutedCard.TLabel",
        background=c["card"],
        foreground=c["muted"],
        font=(c["font_family"], 10),
    )
    style.configure(
        "QDV.Status.Warn.TLabel",
        background=c["bg"],
        foreground=c["warning"],
        font=(c["font_family"], 10, "bold"),
    )
    style.configure(
        "QDV.Status.WarnCard.TLabel",
        background=c["card"],
        foreground=c["warning"],
        font=(c["font_family"], 10, "bold"),
    )
    style.configure(
        "QDV.Status.Error.TLabel",
        background=c["bg"],
        foreground=c["danger"],
        font=(c["font_family"], 11, "bold"),
    )
    style.configure(
        "QDV.Status.Ok.TLabel",
        background=c["bg"],
        foreground=c["success"],
        font=(c["font_family"], 10),
    )

    # --- Botones Neumorphism (raised + hundido al presionar) ---
    try:
        style.configure(
            "TButton",
            padding=(12, 8),
            relief="raised",
            borderwidth=2,
            background=c["card"],
            foreground=c["fg"],
            lightcolor=c["neu_light"],
            darkcolor=c["neu_dark"],
            focusthickness=0,
        )
        style.map(
            "TButton",
            background=[
                ("active", c["card_elevated"]),
                ("pressed", c["bg"]),
                ("disabled", c["neu_mid"]),
            ],
            relief=[("pressed", "sunken"), ("!pressed", "raised")],
            foreground=[("disabled", "#94A3B8")],
        )

        # CTA principal: color vivo, sigue leyendo “presionable”
        style.configure(
            "QDV.Primary.TButton",
            background=c["accent"],
            foreground="#FFFFFF",
            padding=(14, 9),
            relief="raised",
            borderwidth=2,
            lightcolor="#8EA8FF",
            darkcolor=c["accent_pressed"],
        )
        style.map(
            "QDV.Primary.TButton",
            background=[
                ("active", c["accent_hover"]),
                ("pressed", c["accent_pressed"]),
                ("disabled", "#A5B4FC"),
            ],
            foreground=[("disabled", "#E8E8E8")],
            relief=[("pressed", "sunken"), ("!pressed", "raised")],
        )

        # Secundario: superficie card, relieve neu
        style.configure(
            "QDV.Secondary.TButton",
            background=c["card"],
            foreground=c["fg"],
            padding=(12, 8),
            relief="raised",
            borderwidth=2,
            lightcolor=c["neu_light"],
            darkcolor=c["neu_dark"],
        )
        style.map(
            "QDV.Secondary.TButton",
            background=[("active", c["card_elevated"]), ("pressed", c["bg"])],
            relief=[("pressed", "sunken"), ("!pressed", "raised")],
        )

        # Módulos / navegación: más presencia
        style.configure(
            "QDV.NeuModule.TButton",
            background=c["card_elevated"],
            foreground=c["fg"],
            padding=(14, 10),
            relief="raised",
            borderwidth=2,
            lightcolor=c["neu_light"],
            darkcolor=c["neu_dark"],
            font=(c["font_family"], 10, "bold"),
        )
        style.map(
            "QDV.NeuModule.TButton",
            background=[("active", c["card"]), ("pressed", c["bg"])],
            relief=[("pressed", "sunken"), ("!pressed", "raised")],
        )
    except Exception:
        pass

    # Entradas tipo inset (hundidas)
    style.configure(
        "TEntry",
        fieldbackground=c["input_inset"],
        foreground=c["fg"],
        padding=(10, 6),
        borderwidth=2,
        relief="sunken",
        insertcolor=c["accent"],
        lightcolor=c["neu_dark"],
        darkcolor=c["neu_light"],
    )
    style.configure(
        "TCombobox",
        fieldbackground=c["input_inset"],
        foreground=c["fg"],
        padding=(8, 6),
        borderwidth=2,
        relief="sunken",
        arrowsize=14,
        lightcolor=c["neu_dark"],
        darkcolor=c["neu_light"],
    )
    style.map(
        "TCombobox",
        fieldbackground=[("readonly", c["input_inset"])],
        selectbackground=[("readonly", c["input_inset"])],
        selectforeground=[("readonly", c["fg"])],
    )

    style.configure(
        "QDV.Warn.TEntry",
        fieldbackground=c["warn_bg"],
        foreground=c["fg"],
        lightcolor=c["neu_dark"],
        darkcolor=c["neu_light"],
    )
    style.configure(
        "QDV.Error.TEntry",
        fieldbackground=c["error_bg"],
        foreground=c["fg"],
        lightcolor=c["neu_dark"],
        darkcolor=c["neu_light"],
    )

    try:
        style.configure(
            "Vertical.TScrollbar",
            background=c["card"],
            troughcolor=c["bg"],
            borderwidth=1,
            relief="raised",
            lightcolor=c["neu_light"],
            darkcolor=c["neu_dark"],
            arrowsize=12,
        )
        style.configure(
            "Horizontal.TScrollbar",
            background=c["card"],
            troughcolor=c["bg"],
            borderwidth=1,
            relief="raised",
            lightcolor=c["neu_light"],
            darkcolor=c["neu_dark"],
            arrowsize=12,
        )
    except Exception:
        pass

    try:
        style.configure("QDV.Separator.TSeparator", background=c["neu_mid"])
    except Exception:
        pass

    try:
        style.configure(
            "TNotebook.Tab",
            padding=(16, 10),
            font=(c["font_family"], 10, "bold"),
        )
    except Exception:
        pass

    # Treeview: cabecera con toque turquesa
    try:
        style.configure(
            "Treeview",
            background=c["input_bg"],
            fieldbackground=c["input_bg"],
            foreground=c["fg"],
            rowheight=30,
            borderwidth=0,
            relief="flat",
        )
        style.configure(
            "Treeview.Heading",
            background=c["heading_bg"],
            foreground=c["heading_fg"],
            font=(c["font_family"], 10, "bold"),
            relief="raised",
            borderwidth=1,
            lightcolor=c["neu_light"],
            darkcolor=c["teal"],
            padding=(10, 8),
        )
        style.map(
            "Treeview",
            background=[("selected", c["tree_sel_bg"])],
            foreground=[("selected", c["tree_sel_fg"])],
        )
    except Exception:
        pass

    # Checkbuttons en formularios admin
    try:
        style.configure(
            "TCheckbutton",
            background=c["card"],
            foreground=c["fg"],
            focuscolor=c["bg"],
        )
        style.map("TCheckbutton", background=[("active", c["card"])])
    except Exception:
        pass
