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
.POSIX:

bin = rnote
prefix = /usr
version = 0.1.0
files = Makefile COPYING $(bin).py $(bin).1

all: $(bin)

$(bin):
	cp $(bin).py $(bin)
	chmod +x $(bin)

clean:
	rm -f $(bin)

dist:
	tar -czvf rnote_$(version).orig.tar.gz $(files)

install:
	install $(bin) $(DESTDIR)$(prefix)/bin
	install $(bin).1 $(DESTDIR)$(prefix)/share/man/man1

.PHONY: all clean dist install
