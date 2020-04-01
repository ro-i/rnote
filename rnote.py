#!/usr/bin/python3

# rnote - a software to take notes in a simple and convenient way
# Copyright (C) 2019 Robert Imschweiler
#
# This file is part of rnote.
#
# rnote is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# rnote is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with rnote.  If not, see <https://www.gnu.org/licenses/>.

import getopt
import os
import re
import sys
import tempfile
import time
import uuid

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gdk, GLib, GObject, Gtk


app_name = 'rnote'
version_str = 'version 0.1.0'


# global variables
app_dir = '.' + app_name
app_window = None
notes_dir = 'notes'
config_file = 'config'
data_file = 'data'
# constants
copyright = 'Copyright (C) 2019 Robert Imschweiler'
description = 'A software to take notes in a simple and convenient way.'
license_short = 'License GPLv3+: GNU GPL version 3 or later '\
        '<https://gnu.org/licenses/gpl.html>'
license = '''Copyright (C) 2019 Robert Imschweiler

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.'''

help_message = '"'+app_name+'"' + ''' is a software to take notes in a \
simple and convenient way.

The interface is divided in two parts:
The upper one contains the overview with the list of your stored notes. \
The lower one contains a simple editor to create/edit notes.
You may move the separator between these parts in order to resize them. \
This setting will be stored - just as the window size.

These buttons are available:
    delete      delete the currently selected note
    about       show information about this software
    quit        quit the program

    save        save the note you are currently working on
    undo        undo your modifications on the note you are currently working \
on step by step
    redo        redo these modifications step by step
    close       close the note you are currently working on

    You may change the font size of the editor - your selection will be stored.

At any time, you may change the title of the note you are currently working on, \
it will get renamed.'''


class AppWindow:
    # enum
    TEXT_SIZE_MIN = 6
    TEXT_SIZE_MAX = 72

    def __init__(self, window, pane):
        # for external use
        self.window = window
        try:
            self.read()
        except:
            self.update_size(window, None)
            self.update_pane(pane, None)
            self.is_fullscreen = False
            self.is_maximized = False
            self.update_text_size(None)
            return
        pane.set_position(self.pane_position)
        window.set_default_size(self.width, self.height)
        if self.is_fullscreen:
            window.fullscreen()
        if self.is_maximized:
            window.maximize()

    def quit(self):
        self.write()
        Gtk.main_quit()

    def read(self):
        gfile = GLib.KeyFile.new()
        try:
            gfile.load_from_file(config_file, GLib.KeyFileFlags.NONE)
            self.height = gfile.get_integer('WindowState', 'height')
            self.width = gfile.get_integer('WindowState', 'width')
            self.is_maximized = gfile.get_boolean('WindowState', 'is-maximized')
            self.is_fullscreen = gfile.get_boolean('WindowState', 'is-fullscreen')
            self.pane_position = gfile.get_integer('WindowState', 'pane-position')
            self.text_size = gfile.get_integer('WindowState', 'text-size')
            self.text_size_unit = gfile.get_string('WindowState', 'text-size-unit')
        except:
            raise
        finally:
            gfile.unref()

    def update_pane(self, paned, scroll_type):
        self.pane_position = paned.get_position()

    def update_size(self, window, allocation):
        (self.width, self.height) = window.get_size()

    def update_state(self, window, event):
        self.is_fullscreen = bool(event.new_window_state & 
                Gdk.WindowState.FULLSCREEN)
        self.is_maximized = bool(event.new_window_state & 
                Gdk.WindowState.MAXIMIZED)

    def update_text_size(self, new_size):
        if new_size:
            self.text_size = new_size
            return
        try:
            self.text_size = int(
                    Gtk.TextView().get_style_context().get_property(
                        'font-size', Gtk.StateFlags.NORMAL)
                    )
        except:
            self.text_size = 12
        self.text_size_unit = 'px'

    def write(self):
        gfile = GLib.KeyFile.new()
        gfile.set_integer('WindowState', 'height', self.height)
        gfile.set_integer('WindowState', 'width', self.width)
        gfile.set_boolean('WindowState', 'is-maximized', self.is_maximized)
        gfile.set_boolean('WindowState', 'is-fullscreen', self.is_fullscreen)
        gfile.set_integer('WindowState', 'pane-position', self.pane_position)
        gfile.set_integer('WindowState', 'text-size', self.text_size)
        gfile.set_string('WindowState', 'text-size-unit', self.text_size_unit)
        gfile.save_to_file(config_file)
        gfile.unref()


class NoteView:
    def __init__(self, save_func):
        self.widget = self.__create()
        self.save_func = save_func
        self.update()

    def check_save_state(self):
        (name, content) = self.get_content()
        if name == self.name and content == self.content:
            return True
        save = dialog('Save changes before closing?\n'\
                'Otherwise, your changes to this note will be lost.', 
                Gtk.ResponseType.YES)
        if save == 1:
            return self.save()
        elif save == 2:
            return False
        return True

    def close(self, button=None):
        close = self.check_save_state()
        if not close:
            return False
        self.update()
        return True

    def __create_toolbar(self):
        button_save = Gtk.ToolButton.new(None, 'save')
        button_save.connect('clicked', self.save)
        self.button_undo = Gtk.ToolButton.new(None, 'undo')
        self.button_undo.connect('clicked', self.text_buffer.undo)
        self.button_redo = Gtk.ToolButton.new(None, 'redo')
        self.button_redo.connect('clicked', self.text_buffer.redo)
        entry = Gtk.Entry()
        self.entry_buffer = entry.get_buffer()
        entry.set_placeholder_text('name of this note')
        entry_container = Gtk.ToolItem.new()
        entry_container.add(entry)
        entry_container.set_expand(True)
        scale = Gtk.SpinButton.new_with_range(app_window.TEXT_SIZE_MIN, 
                app_window.TEXT_SIZE_MAX, 1)
        scale.set_value(app_window.text_size)
        scale.connect('value-changed', self.scale)
        scale_container = Gtk.ToolItem.new()
        scale_container.add(scale)
        scale_container.set_tooltip_text('change font size')
        button_close = Gtk.ToolButton.new(None, 'close')
        button_close.connect('clicked', self.close)
        toolbar = Gtk.Toolbar.new()
        toolbar.set_style(Gtk.ToolbarStyle.TEXT)
        toolbar.insert(button_save, -1)
        toolbar.insert(self.button_undo, -1)
        toolbar.insert(self.button_redo, -1)
        toolbar.insert(entry_container, -1)
        toolbar.insert(scale_container, -1)
        toolbar.insert(button_close, -1)
        return toolbar

    def __create_textview(self):
        self.text_buffer = UndoRedoTextBuffer()
        self.text_buffer.connect('undo-redo', self.update_buttons)
        textview = Gtk.TextView()
        textview.set_cursor_visible(True)
        textview.set_editable(True)
        textview.set_wrap_mode(Gtk.WrapMode.NONE)
        textview.set_buffer(self.text_buffer)
        return textview

    def __create(self):
        self.textview = self.__create_textview()
        self.scale(None)
        subwin = Gtk.ScrolledWindow()
        subwin.add(self.textview)
        toolbar = self.__create_toolbar()
        box = Gtk.Box.new(Gtk.Orientation.VERTICAL, 0)
        box.pack_start(toolbar, False, False, 0)
        box.pack_start(subwin, True, True, 0)
        return box

    def get_content(self):
        name = self.entry_buffer.get_text()
        (start, end) = self.text_buffer.get_bounds()
        content = self.text_buffer.get_text(start, end, True)
        return (name, content)

    def save(self, button=None):
        (name, content) = self.get_content()
        success = self.save_func(self.name, name, content)
        if not success:
            return False
        self.name = name
        self.content = content
        return True

    def scale(self, button=None):
        if button:
            app_window.update_text_size(button.get_value_as_int())
        provider = Gtk.CssProvider.new()
        provider.load_from_data(
                b'textview { font-size: %d%s; }' %
                (app_window.text_size, app_window.text_size_unit.encode())
                )
        context = self.textview.get_style_context()
        context.add_provider(provider, Gtk.STYLE_PROVIDER_PRIORITY_USER)

    def update(self, name=None, content=None):
        if name:
            self.entry_buffer.set_text(name, -1)
            self.text_buffer.update(content)
        else:
            self.entry_buffer.delete_text(0, -1)
            self.text_buffer.update()
            self.textview.grab_focus()
        (self.name, self.content) = self.get_content()

    def update_buttons(self, widget, undo, redo):
        self.button_undo.set_sensitive(undo)
        self.button_redo.set_sensitive(redo)


class UndoRedoTextBuffer(Gtk.TextBuffer):
    # enum
    INSERT = 1
    DELETE = 2

    def __init__(self):
        super().__init__()
        GObject.signal_new('undo-redo', self, GObject.SignalFlags.RUN_LAST,
                GObject.TYPE_BOOLEAN,
                [GObject.TYPE_BOOLEAN, GObject.TYPE_BOOLEAN])
        self.connect('insert-text', self.__insert)
        self.connect('delete-range', self.__delete)
        self.undo_state = False
        self.redo_state = False

    def update(self, text=None):
        start = self.get_start_iter()
        self.delete(start, self.get_end_iter())
        if text:
            self.do_insert_text(self, start, text, len(text.encode()))
        self.undo_stack = []
        self.redo_stack = []
        self.inform(undo=False, redo=False)

    def append_undo(self, *args):
        self.undo_stack.append(args)
        self.redo_stack = []

    def __delete(self, text_buffer, start_iter, end_iter):
        text = self.get_slice(start_iter, end_iter, True)
        start = start_iter.get_offset()
        end = end_iter.get_offset()
        self.append_undo(self.DELETE, start, end, text, len(text.encode()))
        self.inform(undo=True)

    def __insert(self, text_buffer, start_iter, text, length):
        start = start_iter.get_offset()
        end_iter = self.get_iter_at_mark(self.get_insert())
        end = start+len(text)
        self.append_undo(self.INSERT, start, end, text, length)
        self.inform(undo=True)

    def inform(self, **kwargs):
        if 'undo' in kwargs:
            self.undo_state = kwargs['undo']
        if 'redo' in kwargs:
            self.redo_state = kwargs['redo']
        self.emit('undo-redo', self.undo_state, self.redo_state)

    def redo(self, button):
        (action, start, end, text, length) = self.redo_stack.pop()
        start_iter = self.get_iter_at_offset(start)
        end_iter = self.get_iter_at_offset(end)
        if action == self.INSERT:
            self.do_insert_text(self, start_iter, text, length)
        else:
            self.do_delete_range(self, start_iter, end_iter)
        self.undo_stack.append((action, start, end, text, length))
        self.inform(undo=True)
        if not self.redo_stack:
            self.inform(redo=False)

    def undo(self, button):
        (action, start, end, text, length) = self.undo_stack.pop()
        start_iter = self.get_iter_at_offset(start)
        end_iter = self.get_iter_at_offset(end)
        if action == self.INSERT:
            self.do_delete_range(self, start_iter, end_iter)
        else:
            self.do_insert_text(self, start_iter, text, length)
        self.redo_stack.append((action, start, end, text, length))
        self.inform(redo=True)
        if not self.undo_stack:
            self.inform(undo=False)


class Notes:
    def __init__(self):
        self.read()

    def __get_name_from_gfile(self, filename, gfile):
        try:
            name = gfile.get_string('NotesNames', filename)
        except:
            name = None
        finally:
            return name

    def __get_time(self, filename=None, stat=None):
        if stat:
            st_mtime = stat.st_mtime
        elif filename:
            st_mtime = os.stat(filename).st_mtime
        else:
            raise TypeError('file name or stat information required')
        mtime = time.localtime(st_mtime)
        return time.strftime('%x %H:%M', mtime)

    def note_delete(self, name):
        i = self.names.index(name)
        os.remove(os.path.join(notes_dir, self.list[i][0]))
        del self.names[i]
        del self.list[i]

    def note_get(self, name):
        i = self.names.index(name)
        filename = os.path.join(notes_dir, self.list[i][0])
        with open(filename, 'r') as f:
            return f.read()

    def __note_new(self):
        (fd, filename) = tempfile.mkstemp(prefix='note_', dir=notes_dir)
        os.close(fd)
        self.list.append([os.path.basename(filename), None, None])
        return filename

    def note_rename(self, oldname, name):
        i = self.names.index(oldname)
        self.list[i][1] = self.names[i] = name
        self.sort()

    def note_write(self, name, content):
        try:
            i = self.names.index(name)
        except ValueError:
            filename = self.__note_new()
            i = len(self.list)-1
            self.list[i][1] = name
            self.names.append(name)
        filename = os.path.join(notes_dir, self.list[i][0])
        with open(filename, 'w') as f:
            f.write(content)
        self.list[i][2] = self.__get_time(filename=filename)
        self.sort()

    def repair_names(self):
        self.names = [item[1] for item in self.list]
        for i in range(len(self.list)):
            if self.list[i][1]:
                continue
            while True:
                name = 'unnamed_note_' + uuid.uuid4().hex
                if name not in self.names:
                    break
            self.list[i][1] = self.names[i] = name
        self.sort()

    def read(self):
        self.list = []
        gfile = GLib.KeyFile.new()
        try:
            gfile.load_from_file(data_file, GLib.KeyFileFlags.NONE)
        except:
            gfile.unref()
            gfile = None
        with os.scandir(notes_dir) as _dir:
            for entry in _dir:
                mtime_str = self.__get_time(stat=entry.stat())
                if gfile:
                    name = self.__get_name_from_gfile(entry.name, gfile)
                else:
                    name = None
                self.list.append([entry.name, name, mtime_str])
        if gfile:
            gfile.unref()
        self.repair_names()

    def sort(self):
        # the sort method is guaranteed to be stable
        self.names.sort(key=lambda sort_key: sort_key.lower())
        self.list.sort(key=lambda sort_key: sort_key[1].lower())

    def write(self):
        gfile = GLib.KeyFile.new()
        for (filename, name, mtime_str) in self.list:
            gfile.set_string('NotesNames', filename, name)
        gfile.save_to_file(data_file)
        gfile.unref()


class Overview:
    def __init__(self):
        self.noteview = NoteView(self.save)
        self.widget = self.__create()
        self.notes = Notes()
        self.update()

    def __create(self):
        self.notes_list = self.__create_notes_list()
        subwin = Gtk.ScrolledWindow()
        subwin.add(self.notes_list)
        sep = Gtk.Separator.new(Gtk.Orientation.HORIZONTAL)
        box = Gtk.Box.new(Gtk.Orientation.VERTICAL, 0)
        box.pack_start(self.__create_toolbar(), False, False, 0)
        box.pack_start(sep, False, False, 0)
        box.pack_start(subwin, True, True, 0)
        return box

    def __create_notes_list(self):
        view = Gtk.TreeView.new_with_model(Gtk.ListStore(str, str))
        view.connect('row-activated', self.open_note)
        view.get_selection().set_mode(Gtk.SelectionMode.SINGLE)
        cols = ['Note', 'Time']
        for i in range(2):
            col = Gtk.TreeViewColumn(cols[i], Gtk.CellRendererText(), text = i)
            col.set_resizable(True)
            col.set_min_width(10)
            if cols[i] == 'Note':
                col.set_expand(True)
            view.append_column(col)
        return view

    def __create_toolbar(self):
        button_delete = Gtk.ToolButton.new(None, 'delete')
        button_delete.connect('clicked', self.delete_note)
        space = Gtk.SeparatorToolItem.new()
        space.set_draw(False)
        space.set_expand(True)
        button_help = Gtk.ToolButton.new(None, 'help')
        button_help.connect('clicked', dialog_message, 'help', help_message)
        button_about = Gtk.ToolButton.new(None, 'about')
        button_about.connect('clicked', about)
        button_quit = Gtk.ToolButton.new(None, 'quit')
        button_quit.connect('clicked', self.quit)
        toolbar = Gtk.Toolbar.new()
        toolbar.set_style(Gtk.ToolbarStyle.TEXT)
        toolbar.insert(button_delete, -1)
        toolbar.insert(space, -1)
        toolbar.insert(button_help, -1)
        toolbar.insert(button_about, -1)
        toolbar.insert(button_quit, -1)
        return toolbar

    def delete_note(self, button):
        (model, _iter) = self.notes_list.get_selection().get_selected()
        if not _iter:
            return
        name = model[_iter][0]
        if name == self.noteview.name:
            dialog_message(title='Warning',
                    msg='Error: This note is currently open', textview=False)
            return
        delete = dialog('Do you really want to delete %s?' % name, 
                Gtk.ResponseType.NO)
        if delete != 1:
            return
        try:
            self.notes.note_delete(name)
        except:
            return
        self.update()

    def open_note(self, tree_view, path, column):
        model = tree_view.get_model()
        name = model[path][0]
        closed = self.noteview.close()
        if not closed:
            return
        self.noteview.update(name, self.notes.note_get(name))

    def quit(self, widget=None, event=None):
        close = self.noteview.check_save_state()
        if not close:
            # stop the event by returning True
            return True
        self.notes.write()
        app_window.quit()

    # Be aware: changing the name of a note should not create a new one, but
    # should rename the current one. The only exception is, when the note has
    # no name yet (i.e., the user created a new note). After giving a name to
    # a new note, however, changing this name should result in a renaming.
    def save(self, oldname, name, content):
        if not name:
            dialog_message(title='Error Message', 
                    msg='Error: this note has no name', textview=False)
            return False
        elif oldname != name and name in self.notes.names:
            overwrite = dialog(
                    'There already is a note with the name \'%s\'.\n'
                    'Do you like to overwrite it?' % name, 
                    Gtk.ResponseType.CANCEL)
            if overwrite != 1:
                return False
        if oldname != name and oldname:
            self.notes.note_rename(oldname, name)
        else:
            oldname = name
        self.notes.note_write(name, content)
        self.update()
        return True

    def update(self):
        model = self.notes_list.get_model()
        model.clear()
        for (filename, name, time) in self.notes.list:
            model.append([name, time])


def about(button):
    dialog = Gtk.AboutDialog.new()
    dialog.set_resizable(True)
    dialog.set_program_name('note')
    dialog.set_version(version_str)
    dialog.set_copyright(copyright)
    dialog.set_comments(description)
    dialog.set_license(license)
    dialog.set_logo_icon_name()
    dialog.run()
    dialog.destroy()


def create_gui():
    global app_window

    window = Gtk.Window.new(Gtk.WindowType.TOPLEVEL)
    pane = Gtk.Paned.new(Gtk.Orientation.VERTICAL)
    # track window state
    app_window = AppWindow(window, pane)
    overview = Overview()

    window.connect('delete-event', overview.quit)
    window.connect('size-allocate', app_window.update_size)
    window.connect('window-state-event', app_window.update_state)
    window.set_border_width(4)
    window.set_position(Gtk.WindowPosition.CENTER_ALWAYS)
    window.set_title(app_name)

    pane.pack1(overview.widget, True, False)
    pane.pack2(overview.noteview.widget, True, False)
    pane.connect('notify::position', app_window.update_pane)
    window.add(pane)

    window.show_all()


def dialog_message(widget=None, title='', msg='', textview=True):
    dialog = Gtk.MessageDialog(
            title=title,
            parent=app_window.window,
            modal=True,
            destroy_with_parent=True,
            buttons=Gtk.ButtonsType.OK,
            )
    dialog.set_resizable(True)
    dialog.set_transient_for(app_window.window)
    if textview:
        text_view = Gtk.TextView.new()
        text_view.set_cursor_visible(False)
        text_view.set_editable(False)
        text_view.set_wrap_mode(Gtk.WrapMode.WORD)
        text_view.get_buffer().set_text(msg)
        view = Gtk.ScrolledWindow.new()
        view.add(text_view)
        view.set_min_content_width(500)
        view.set_min_content_height(300)
    else:
        view = Gtk.Label.new(msg)
    box = dialog.get_content_area()
    box.pack_start(view, True, True, 0)
    dialog.show_all()
    dialog.run()
    dialog.destroy()


def dialog(msg, default_response):
    dialog = Gtk.Dialog(
            title='Warning',
            parent=app_window.window,
            modal=True,
            destroy_with_parent=True
            )
    dialog.add_buttons(
            "No",
            Gtk.ResponseType.NO,
            "Cancel",
            Gtk.ResponseType.CANCEL,
            "Yes",
            Gtk.ResponseType.YES
            )
    dialog.set_default_response(default_response)
    dialog.set_resizable(True)
    dialog.set_transient_for(app_window.window)
    box = dialog.get_content_area()
    box.pack_start(Gtk.Label.new(msg), False, False, 0)
    dialog.show_all()
    response = dialog.run()
    dialog.destroy()
    if response == Gtk.ResponseType.NO:
        return 0
    elif response == Gtk.ResponseType.YES:
        return 1
    else:
        return 2


def die(error):
    sys.exit('%s: %s' % (sys.argv[0], error))


def setup():
    global app_dir, config_file, data_file, notes_dir

    def check_dir(dirname):
        if os.path.isdir(dirname):
            return
        try:
            os.mkdir(dirname, 448)
        except:
            die('Cannot create %s' % dirname)

    try:
        home_dir = os.environ['HOME']
    except:
        die('Could not get the name of your home directory')

    app_dir = os.path.join(home_dir, app_dir)
    config_file = os.path.join(app_dir, config_file)
    data_file = os.path.join(app_dir, data_file)
    notes_dir = os.path.join(app_dir, notes_dir)
    check_dir(app_dir)
    check_dir(notes_dir)


def usage():
    print('usage: ' + app_name + ' [options]\n'
            '  -h --help\t\tprint this help\n'
            '  -v --version\t\tprint version information'
            )


def version():
    print(app_name + ', ' + version_str + '\n'
            + copyright + '\n'
            + license_short + '\n'
            'This program comes with ABSOLUTELY NO WARRANTY.\n'
            'This is free software, and you are welcome to redistribute it '
            'under certain conditions.\n'
            'For further information, use the \'about\' utility in the GUI.'
            )


try:
    (opts, args) = getopt.getopt(sys.argv[1:], 'hv', [ 'help', 'version', ])
except getopt.GetoptError as err:
    die(err)
for o, a in opts:
    if o in ('-h', '--help'):
        usage()
        sys.exit(0)
    elif o in ('-v', '--version'):
        version()
        sys.exit(0)
if args:
    die('unhandled option(s): %s' % ' '.join(args))


setup()
create_gui()
Gtk.main()
