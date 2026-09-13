// The rice list -- what the desktop's reading card names as newly landed --
// as a CUE package. catalogue.cue is the list itself; this file is what an
// entry has to be, written down once: the same rules rice_tour.check()
// applies when the card loads ~/.config/oldbook/rice.json, so a mistake is
// caught by `cue vet` before it is ever rendered.
//
// rice.json is rendered from here, byte for byte:
//
//     cue vet ./alpine/cue/rice
//     cue export ./alpine/cue/rice -e rice --out json \
//         > alpine/desktop/.config/oldbook/rice.json
//
// test_rice_tour checks that the shipped file is exactly that output, so the
// list cannot drift from its source. The wider render-and-apply pipeline
// (alpine/bin/cue-render and cue-sync, with a watcher that pulls and applies
// on every commit) is being built alongside this; the package needs nothing
// but `cue export`, so it can be wired in as a whole-file target.
package rice

import (
	"list"
	"strings"
)

#Entry: {
	// A lowercase hyphenated id: the key the card keeps its ticks by.
	id: string & =~"^[a-z0-9][a-z0-9-]{0,47}$"
	// The row on the card, cut with an ellipsis past forty-six characters.
	title: string & =~"\\S"
	date:  string & =~"^[0-9]{4}-(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])$"
	// Two lines of fifty characters on the card. test_rice_tour checks the
	// exact wrap; this is the coarse bound that catches an essay.
	summary: string & =~"\\S" & strings.MaxRunes(100)
	// How to set it off, in words; the terminal listing shows all of it.
	trigger: string & =~"\\S"
	// More words for the notification and the terminal, never for the card.
	detail?: string
	// What the Try link runs, detached, instead of only saying how.
	run?: list.MinItems(1) & [...string & !=""]
	// A run that prints rather than draws asks for a terminal.
	terminal?: bool
}

#List: {
	version: 1
	// Newest first within a day: the loader sorts by date and keeps file
	// order, which is why a new feature goes at the top of catalogue.cue.
	entries: [...#Entry]
	// Ids are unique: the set of them is exactly as large as the list.
	_ids: {for entry in entries {(entry.id): true}}
	_unique: len(_ids) == len(entries)
	_unique: true
}

rice: #List
