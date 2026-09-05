"""Result window and settings (GTK4 / libadwaita)."""

import io
import os
import sys
import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Adw, Gdk, GdkPixbuf, Gio, GLib, Gtk  # noqa: E402

from . import (autostart, capture, config, fonts, keyring_store, notify,  # noqa: E402
               offline, pipeline, translate)
from .i18n import APP_NAME, _  # noqa: E402

APP_ID = "cz.polyweb.LinuxScreenTranslator"

# DeepL target codes paired with names shown in the settings.
LANGUAGES = [
    ("CS", _("Czech")), ("SK", _("Slovak")), ("EN-GB", _("English (UK)")),
    ("EN-US", _("English (US)")), ("DE", _("German")), ("PL", _("Polish")),
    ("FR", _("French")), ("ES", _("Spanish")), ("IT", _("Italian")),
    ("UK", _("Ukrainian")), ("PT-PT", _("Portuguese")), ("NL", _("Dutch")),
]

MAX_WINDOW = (1500, 950)

SERVICES = [("deepl", _("DeepL (online)")), ("offline", _("Offline, on this machine"))]


def texture_from_pil(image):
    """Convert a PIL.Image into a Gdk.Texture that Gtk.Picture can show."""
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    loader = GdkPixbuf.PixbufLoader.new_with_type("png")
    loader.write(buffer.getvalue())
    loader.close()
    return Gdk.Texture.new_for_pixbuf(loader.get_pixbuf())


class TranslationWindow(Adw.ApplicationWindow):
    """The single window of a run: progress first, then the result.

    It is presented before the work starts. Mapping the window right after the
    user finished selecting an area is what earns it the focus — a window that
    appears seconds later is held back by the shell's focus-stealing
    prevention and silently ends up behind everything else.
    """

    def __init__(self, app, image_path, cfg, api_key):
        super().__init__(application=app, title=APP_NAME)
        self._cfg = cfg
        self._image_path = image_path
        self._api_key = api_key
        self._result = None
        self._translated = None

        from PIL import Image
        self._source = Image.open(image_path).convert("RGB")
        self._original = texture_from_pil(self._source)

        width, height = self._source.size
        scale = min(MAX_WINDOW[0] / width, MAX_WINDOW[1] / (height + 120), 1.0)
        self.set_default_size(max(480, int(width * scale)), max(360, int(height * scale) + 120))

        self._picture = Gtk.Picture(vexpand=True)
        self._picture.set_content_fit(Gtk.ContentFit.CONTAIN)
        self._picture.set_paintable(self._original)

        header = Adw.HeaderBar()
        self._compare = Gtk.ToggleButton(
            icon_name="view-reveal-symbolic",
            tooltip_text=_("Show the original (hold space)"),
        )
        self._compare.connect("toggled", self._on_compare)
        self._compare.set_sensitive(False)
        header.pack_start(self._compare)

        self._buttons = []
        settings = Gtk.Button(icon_name="emblem-system-symbolic", tooltip_text=_("Settings"))
        settings.connect("clicked", self._on_settings)
        header.pack_end(settings)

        self._save = Gtk.MenuButton(icon_name="document-save-symbolic",
                                    tooltip_text=_("Save… (Ctrl+S)"),
                                    menu_model=self._build_save_menu())
        self._save.set_sensitive(False)
        header.pack_end(self._save)
        self._buttons.append(self._save)

        copy = Gtk.Button(icon_name="edit-copy-symbolic",
                          tooltip_text=_("Copy to clipboard (Ctrl+C)"))
        copy.connect("clicked", self._on_copy)
        copy.set_sensitive(False)
        header.pack_end(copy)
        self._buttons.append(copy)

        # "busy" while the pipeline runs, then either "result" or "status".
        self._stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        self._stack.add_named(self._build_busy_page(), "busy")
        self._stack.set_visible_child_name("busy")

        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(header)
        toolbar.set_content(self._stack)

        self._toasts = Adw.ToastOverlay(child=toolbar)
        self.set_content(self._toasts)
        self._install_shortcuts()

    def start(self):
        """Show the window, then do the work on a background thread."""
        self.present()
        threading.Thread(target=self._work, daemon=True).start()

    def _build_busy_page(self):
        self._busy = Adw.StatusPage(title=_("Translating…"))
        spinner = Gtk.Spinner(spinning=True, width_request=32, height_request=32)
        self._busy.set_child(spinner)
        return self._busy

    def _work(self):
        try:
            result = pipeline.process(
                self._image_path, self._cfg, api_key=self._api_key,
                progress=lambda message: GLib.idle_add(self._busy.set_description, message),
            )
        except pipeline.NoTextFound:
            GLib.idle_add(self._show_status, "edit-find-symbolic", _("Nothing to translate"),
                          _("No text was found in the selected area."))
        except translate.TranslationError as exc:
            GLib.idle_add(self._show_status, "dialog-warning-symbolic",
                          _("Translation failed"), str(exc))
        except Exception as exc:  # noqa: BLE001 - never leave the window spinning
            GLib.idle_add(self._show_status, "dialog-error-symbolic",
                          _("Something went wrong"), str(exc))
        else:
            GLib.idle_add(self._finish, result)
        finally:
            if not self._cfg.get("keep_capture", False):
                try:
                    import os
                    os.remove(self._image_path)
                except OSError:
                    pass
        return False

    def _show_status(self, icon, title, description):
        """Replace the spinner with an explanation, and say so system-wide too."""
        page = Adw.StatusPage(icon_name=icon, title=title, description=description)
        self._stack.add_named(page, "status")
        self._stack.set_visible_child_name("status")
        notify.send(title, description)
        return False

    def _finish(self, result):
        self._result = result
        if not any(g.translated.strip() for g in result.groups):
            # Text was recognised, but all of it already is in the target
            # language, so nothing was replaced.
            return self._show_status(
                "emblem-ok-symbolic", _("Nothing to translate"),
                _("The text found is already in the target language."))

        self._translated = texture_from_pil(result.image)
        self._picture.set_paintable(self._translated)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.append(self._picture)
        box.append(self._build_text_list())
        self._stack.add_named(box, "result")
        self._stack.set_visible_child_name("result")

        self._compare.set_sensitive(True)
        for button in self._buttons:
            button.set_sensitive(True)
        return False

    def _build_text_list(self):
        """An expander under the image listing original and translation."""
        listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        listbox.add_css_class("boxed-list")
        for group in self._result.groups:
            row = Adw.ActionRow(title=GLib.markup_escape_text(group.translated),
                                subtitle=GLib.markup_escape_text(group.text))
            row.set_subtitle_lines(2)
            row.set_title_lines(2)
            listbox.append(row)

        scrolled = Gtk.ScrolledWindow(child=listbox, max_content_height=220,
                                      propagate_natural_height=True)
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        expander = Gtk.Expander(
            label=_("Recognised text — {summary}").format(summary=self._result.summary))
        expander.set_child(scrolled)
        expander.set_margin_start(12)
        expander.set_margin_end(12)
        expander.set_margin_bottom(12)
        return expander

    def _install_shortcuts(self):
        controller = Gtk.ShortcutController()
        for accel, callback in (
            ("<Control>c", self._on_copy),
            ("<Control>s", lambda *_a: self._on_save(what="translation")),
            ("Escape", lambda *_a: self.close()),
        ):
            controller.add_shortcut(Gtk.Shortcut(
                trigger=Gtk.ShortcutTrigger.parse_string(accel),
                action=Gtk.CallbackAction.new(lambda *_a, cb=callback: (cb(None), True)[1]),
            ))
        self.add_controller(controller)

        # Holding space previews the original for as long as it is held down.
        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self._on_key, True)
        keys.connect("key-released", self._on_key, False)
        self.add_controller(keys)

    def _on_key(self, _controller, keyval, _code, _state, pressed):
        if keyval == Gdk.KEY_space and self._translated is not None:
            self._compare.set_active(pressed)
            return True
        return False

    def _on_compare(self, button):
        if self._translated is None:
            return
        self._picture.set_paintable(self._original if button.get_active() else self._translated)

    def _toast(self, message):
        self._toasts.add_toast(Adw.Toast(title=message, timeout=3))

    def _on_copy(self, _button):
        if self._translated is None:
            return
        self.get_clipboard().set_texture(self._translated)
        self._toast(_("Copied to clipboard"))

    def _build_save_menu(self):
        """Both the translation and the untouched capture can be kept."""
        menu = Gio.Menu()
        menu.append(_("Save translation"), "win.save-translation")
        menu.append(_("Save original"), "win.save-original")
        menu.append(_("Save both"), "win.save-both")

        actions = Gio.SimpleActionGroup()
        for name in ("save-translation", "save-original", "save-both"):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", self._on_save, name.replace("save-", ""))
            actions.add_action(action)
        self._save_actions = actions   # held so it can be inspected and stays alive
        self.insert_action_group("win", actions)
        return menu

    def _on_save(self, _action=None, _param=None, what="translation"):
        if self._result is None:
            return
        suggested = "original.png" if what == "original" else "translation.png"
        dialog = Gtk.FileDialog(initial_name=suggested)

        def done(source, task):
            try:
                path = source.save_finish(task).get_path()
            except GLib.Error:
                return  # cancelled by the user
            self._write(path, what)

        dialog.save(self, None, done)

    def _write(self, path, what):
        if what == "original":
            self._source.save(path)
            return self._toast(_("Saved to {path}").format(path=path))
        if what == "translation":
            self._result.image.save(path)
            return self._toast(_("Saved to {path}").format(path=path))

        # Both: the chosen name for the translation, and a sibling beside it.
        root, extension = os.path.splitext(path)
        companion = f"{root}-original{extension or '.png'}"
        self._result.image.save(path)
        self._source.save(companion)
        return self._toast(_("Saved alongside {path}").format(path=companion))

    def _on_settings(self, _button):
        PreferencesDialog().present(self)


class PreferencesUI:
    """Settings content: target language, DeepL key and behaviour.

    The same content backs both the dialog and the standalone window.
    """

    def __init__(self):
        self._cfg = config.load()
        self.page = Adw.PreferencesPage()
        self.page.add(self._translation_group())
        self.page.add(self._behaviour_group())

    def _translation_group(self):
        group = Adw.PreferencesGroup(title=_("Translation"))

        codes = [code for code, _label in LANGUAGES]
        self._lang = Adw.ComboRow(
            title=_("Target language"),
            model=Gtk.StringList.new([label for _code, label in LANGUAGES]),
        )
        current = self._cfg.get("target_lang", "CS")
        self._lang.set_selected(codes.index(current) if current in codes else 0)
        self._lang.connect("notify::selected", self._on_lang)
        group.add(self._lang)

        codes = [code for code, _label in SERVICES]
        self._service = Adw.ComboRow(
            title=_("Translation service"),
            model=Gtk.StringList.new([label for _code, label in SERVICES]),
        )
        current_service = self._cfg.get("translator", "deepl")
        self._service.set_selected(codes.index(current_service) if current_service in codes else 0)
        self._service.connect("notify::selected", self._on_service)
        group.add(self._service)

        self._model_row = Adw.ActionRow(title=_("Offline model"))
        self._model_get = Gtk.Button(label=_("Download"), valign=Gtk.Align.CENTER)
        self._model_get.connect("clicked", self._on_get_model)
        self._model_row.add_suffix(self._model_get)
        group.add(self._model_row)

        self._font_row = Adw.ActionRow(title=_("Typeface"))
        self._font_auto = Gtk.Button(icon_name="edit-undo-symbolic", valign=Gtk.Align.CENTER,
                                     tooltip_text=_("Back to the automatic choice"))
        self._font_auto.add_css_class("flat")
        self._font_auto.connect("clicked", self._on_auto_font)
        choose = Gtk.Button(label=_("Choose…"), valign=Gtk.Align.CENTER)
        choose.connect("clicked", self._on_choose_font)
        self._font_row.add_suffix(choose)
        self._font_row.add_suffix(self._font_auto)
        group.add(self._font_row)
        self._refresh_font_row()

        self._key = Adw.PasswordEntryRow(title=_("DeepL API key"))
        self._key.set_text(keyring_store.lookup() or self._cfg.get("deepl_api_key", ""))
        self._key.connect("changed", self._on_key_changed)
        group.add(self._key)

        self._meter = Gtk.ProgressBar(valign=Gtk.Align.CENTER, width_request=170)
        self._meter.set_visible(False)
        self._check = Gtk.Button(icon_name="view-refresh-symbolic",
                                 valign=Gtk.Align.CENTER,
                                 tooltip_text=_("Check the key and refresh the quota"))
        self._check.add_css_class("flat")
        self._check.connect("clicked", self._on_check)

        row = Adw.ActionRow(
            title=_("Monthly quota"),
            subtitle=_("The key is kept in the system keyring, not in the config file."),
        )
        row.add_suffix(self._meter)
        row.add_suffix(self._check)
        self._status_row = row
        group.add(row)

        # Fill it in on open: how much is left matters before a translation is
        # attempted, not only when someone thinks to press a button.
        self._on_check()
        self._refresh_service()
        return group

    def _source(self):
        return self._cfg.get("source_lang") or "EN"

    def _refresh_service(self):
        """Show only what the chosen service needs."""
        online = self._cfg.get("translator", "deepl") != "offline"
        for row in (self._key, self._status_row):
            row.set_visible(online)
        self._model_row.set_visible(not online)
        if online:
            return

        source, target = self._source(), self._cfg.get("target_lang", "CS")
        pair = f"{translate.base_lang(source)} → {translate.base_lang(target)}"
        if offline.is_installed(source, target):
            self._model_row.set_subtitle(_("{pair} is ready.").format(pair=pair))
            self._model_get.set_visible(False)
        else:
            self._model_row.set_subtitle(
                _("{pair} is not installed — about 65 MB.").format(pair=pair))
            self._model_get.set_visible(True)

    def _on_service(self, row, _param):
        self._cfg["translator"] = SERVICES[row.get_selected()][0]
        config.save(self._cfg)
        self._refresh_service()

    def _on_get_model(self, _button):
        self._model_get.set_sensitive(False)
        source, target = self._source(), self._cfg.get("target_lang", "CS")

        def worker():
            try:
                offline.download(source, target,
                                 progress=lambda m: GLib.idle_add(self._model_row.set_subtitle, m))
                GLib.idle_add(finish, None)
            except translate.TranslationError as exc:
                GLib.idle_add(finish, str(exc))

        def finish(error):
            self._model_get.set_sensitive(True)
            if error:
                self._model_row.set_subtitle("❌ " + error)
            else:
                self._refresh_service()
            return False

        threading.Thread(target=worker, daemon=True).start()

    def _behaviour_group(self):
        group = Adw.PreferencesGroup(title=_("Behaviour"))

        self._inpaint = Adw.SwitchRow(
            title=_("Erase the original text"),
            subtitle=_("Fills in the background underneath. When off, the "
                       "translation is drawn over the original."),
            active=self._cfg.get("inpaint", True),
        )
        self._inpaint.connect("notify::active", self._on_switch, "inpaint")
        group.add(self._inpaint)

        self._autostart = Adw.SwitchRow(
            title=_("Start with the session"),
            subtitle=_("Puts the icon back in the top bar after logging in."),
            active=autostart.is_enabled(),
        )
        self._autostart.connect("notify::active", self._on_autostart)
        group.add(self._autostart)

        self._keep = Adw.SwitchRow(
            title=_("Keep the captures"),
            subtitle=_("The desktop saves every capture into your Screenshots folder."),
            active=self._cfg.get("keep_capture", False),
        )
        self._keep.connect("notify::active", self._on_switch, "keep_capture")
        group.add(self._keep)
        return group

    def _on_lang(self, row, _param):
        self._cfg["target_lang"] = LANGUAGES[row.get_selected()][0]
        config.save(self._cfg)
        self._refresh_font_row()
        self._refresh_service()

    def _refresh_font_row(self):
        """Say which typeface will be used, and warn when it cannot draw."""
        target = self._cfg.get("target_lang", "CS")
        configured = self._cfg.get("font_path", "")
        path = fonts.for_language(target, configured)
        name = os.path.basename(path)

        if fonts.can_render(path, fonts.sample_for(target)):
            origin = _("chosen by hand") if configured else _("picked for the target language")
            self._font_row.set_subtitle(f"{name} — {origin}")
        else:
            # Worth spelling out: a font without the glyphs does not fail, it
            # quietly draws empty boxes.
            self._font_row.set_subtitle("⚠ " + _(
                "{font} has no glyphs for this language — the text would come "
                "out as empty boxes").format(font=name))
        self._font_auto.set_sensitive(bool(configured))

    def _on_auto_font(self, _button):
        self._cfg["font_path"] = ""
        config.save(self._cfg)
        self._refresh_font_row()

    def _on_choose_font(self, _button):
        dialog = Gtk.FileDialog(title=_("Choose a typeface"))
        filters = Gio.ListStore.new(Gtk.FileFilter)
        font_filter = Gtk.FileFilter(name=_("Fonts"))
        for pattern in ("*.ttf", "*.otf", "*.ttc"):
            font_filter.add_pattern(pattern)
        filters.append(font_filter)
        dialog.set_filters(filters)

        def done(source, task):
            try:
                path = source.open_finish(task).get_path()
            except GLib.Error:
                return  # cancelled
            self._cfg["font_path"] = path
            config.save(self._cfg)
            self._refresh_font_row()

        dialog.open(self._font_row.get_root(), None, done)

    def _on_autostart(self, row, _param):
        """Write or remove the autostart entry, and start the icon right away.

        Waiting until the next login to see any effect would make the switch
        look broken.
        """
        ok = autostart.enable() if row.get_active() else autostart.disable()
        if not ok:
            row.set_subtitle("⚠ " + _("Could not change the autostart entry."))
            return
        if row.get_active():
            self._autostart.set_subtitle(
                _("Puts the icon back in the top bar after logging in."))

    def _on_switch(self, row, _param, key):
        self._cfg[key] = row.get_active()
        config.save(self._cfg)

    def _on_key_changed(self, entry):
        api_key = entry.get_text().strip()
        if keyring_store.store(api_key):
            self._cfg["deepl_api_key"] = ""      # never keep it in the file
        else:
            self._cfg["deepl_api_key"] = api_key
        config.save(self._cfg)

    def _on_check(self, _button=None):
        api_key = self._key.get_text().strip()
        if not api_key:
            self._meter.set_visible(False)
            self._status_row.set_subtitle(_("Enter a key to see the remaining quota."))
            return

        self._check.set_sensitive(False)
        self._status_row.set_subtitle(_("Checking…"))

        def worker():
            usage = translate.check_key(api_key)
            GLib.idle_add(finish, usage)

        def finish(usage):
            self._check.set_sensitive(True)
            self._meter.set_visible(usage.ok)
            if not usage.ok:
                self._status_row.set_subtitle("❌ " + usage.message)
                return False
            self._meter.set_fraction(usage.fraction)
            warning = "⚠ " if usage.fraction >= 0.9 else ""
            self._status_row.set_subtitle(warning + usage.message)
            return False

        threading.Thread(target=worker, daemon=True).start()


class PreferencesDialog(Adw.PreferencesDialog):
    """Settings shown over the result window."""

    def __init__(self):
        super().__init__(title=_("Settings"))
        self.set_search_enabled(False)
        self._ui = PreferencesUI()   # hold a reference so the handlers stay alive
        self.add(self._ui.page)


class PreferencesWindow(Adw.Window):
    """Standalone settings window used by --settings.

    Settings used to open as a dialog over an empty host window that had no
    header bar. GTK draws a solid grey frame around such a window instead of a
    transparent shadow, so the shell is gone and this is a real window.
    """

    def __init__(self, app):
        super().__init__(application=app, title=_("Settings — {name}").format(name=APP_NAME),
                         default_width=580, default_height=560)
        self._ui = PreferencesUI()
        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(Adw.HeaderBar())
        toolbar.set_content(self._ui.page)
        self.set_content(toolbar)


def run_grab():
    """Capture an area, then hand it to the window, which does the rest."""
    cfg = config.load()
    path = capture.take_screenshot(interactive=True)
    if not path:
        return 0

    api_key = keyring_store.lookup() or cfg.get("deepl_api_key")
    app = Adw.Application(application_id=APP_ID, flags=Gio.ApplicationFlags.NON_UNIQUE)
    app.connect("activate", lambda a: TranslationWindow(a, path, cfg, api_key).start())
    return app.run([])


def run_settings():
    app = Adw.Application(application_id=APP_ID + ".settings",
                          flags=Gio.ApplicationFlags.NON_UNIQUE)
    app.connect("activate", lambda application: PreferencesWindow(application).present())
    return app.run([])


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    Adw.init()
    if "--settings" in argv:
        return run_settings()
    return run_grab()
