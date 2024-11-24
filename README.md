# What is Taskwarrior-JP ?

Taskwarrior-JP (short: "TJP") is a python script that gives a CLI interface to Joplin's todo-notes in an efficient manner.

Taskwarrior-JP will allow you to see your todo-notes, to search them (thanks to filtering), to mark them as "done", and to create some.

TJP is very much inspired by [Taskwarrior](https://taskwarrior.org/).

# Quickstart

## Prerequisites

First, git clone (or download) this repository.

Then install the requirements `pip install -r requirements` (or manually download `prettytable.py` and save it in the same folder as `tjp.py`).

Start your Joplin App and enable the "WebClipper" option (if you haven't already :)).
You also want to take note of the Web Clipper token.
That's in the "Tools > Options" menu within Joplin, then "Web Clipper" in the left taskbar.

Copy `tjp.ini.sample` as `tjp.ini` in the same folder as `tjp.py` then open it and replace `Enter_your_joplin_token_here` with your Web Clipper token.
Note : this step is optionnal ; if you prefer, you can pass the token as a command-line argument to `tjp.py` each time you call it : `tjp.py --token=your_WebClipper_token ...`.

## Basic usage : list, create, search, mark as done

### Listing todo-notes

If you execute `./tjp.py`, you should see a list of all the todo-notes that are currently not tagged as "done" within your Joplin App.

### Creating todo-notes

If you execute `./tjp.py add "This is the title of my new todo"`, Taskwarrior-JP will create a new todo-note in your Joplin App (in the root notebook).
The title of this new note will be "This is the title of my new todo".

### Search todo-notes

If you execute `./tjp.py lorem`, you should see a list of all the todo-notes which have the string "lorem" in their title (obviously, you should change the word "lorem" for something that's relevant to what you are searching for : `./tjp.py buy`, `./tjp.py john`, etc.).
That's a very simple search feature but it should be enough for most beginners.
You'll learn more advanced search methods (using tags, projects, and metadata) later in this README.

### Marking a todo-note as "done"

When you list todo-notes, you should see the first column named "ID". 
These IDs are used to reference your todo-notes.
Therefore, if your newly created task has ID "b42", this is how you tell Taskwarrior-JP that you want to deal with it : `./tjp.py b42`.

Knowing all this, this is how you mark the task with ID "b42" as "done" : `./tjp.py b42 done`.

### Summary

 * `./tjp.py` will list your tasks (in a "smart" order)
 * `./tjp.py add "Clean my messy code"` will add a task (with title "Clean my messy code")
 * `./tjp.py 123 done` will mark task of ID "123" as done.

## Common usage : modifying todo, using tags and metadata

### Modifying a todo

To modify the title of a todo-note (which id is, for example, 69) : `./tjp.py 69 modify "This will be the new title of this todo-note (with ID 69)"`

### Using tags

As in Taskwarrior, you can add TAGS to each todo-note.
It is important to know that, at least for now, Taskwarrior-JP's tags and Joplin's tags are two completely different things and are not synced in any way. 
Another way of saying it is that Taskwarrior-JP completely ignores Joplin's tags.

To create a todo-note with the tag "work" : `./tjp.py add +work "This is a task related to work...I guess."` 

If you forgot to add the tag when creating a note (like the one with ID "69"), don't worry !
You already know how to modify todo-notes, so just adding the tag "work" to it is simple : `./tjp.py 69 modify +work`.

If you screwed up and want to remove the tag "work" from a todo-notes (such as the one with ID 69), easy peasy : `./tjp.py 69 modify -work`.

Finally, you can use tags to filter what todo-notes are displayed by Taskwarrior-JP :
 * `./tjp.py +work` will show you only the notes that are tagged "work"
 * `./tjp.py -work` will show you only the notes that are **not** tagged "work"
 * `./tjp.py -work +lazy` will show only the notes that are not tagged "work" but are tagged "lazy".

Obviously, when you "create" or "modify" you can specify multiple tags at once : 
 * `./tjp.py add +demo +easy +writing "Write a nice README for Taskwarrior-JP"`
 * `./tjp.py 234 modify -work +personnal +cooking`

### Metadata

As in Taskwarrior, you can add some metadata to your todo-notes.
Taskwarrior-JP is way less powerfull than Taskwarrior but, for now, I'm fine with that subset of features.

An example of metadata is the "priority".
If you want to add a priority (either "L" for low, "M" for medium, or "H" for high) to the todo-note with id "ff16" : `./tjp.py ff16 modify priority:H`

You also you can remove a metadata if you change your mind : `./tjp.py ff16 modify priority:`

Obviously, you could have specified this metadata when you created the todo-note : `./tjp.py add priority:H "Doing something very important"`

You can also use the metadata to filter what is displayed : 
 * `./tjp.py priority:H` will show only todo-notes with a "H" priority
 * `./tjp.py -priority:L` whill show only todo-notes that are **not** of priority "L"
 * `./tjp.py priority:` will show only todo-notes that have a priority defined (whatever the priority is)
 * `./tjp.py -priority:` will show only todo-notes that have no priority defined (I know these last 2 are confusing)

Here are all the currently "usable" metadata :
 * priority : this can take value "L" (low), "M" (medium), or "H" (high).
 * due : a date or datetime (format MUST BE "YYYY-MM-DD" or "YYYY-MM-DD HH:mm")
 * project : a project's name (usefull to group related tasks)
 * depends : more on this in the "advanced" part.

You can also define any other metadata (ex: `./tjp.py ff16 modify mysupermeta:valueofdoom`) but they will not be treated specially (they won't alter the priority of tasks, etc.) and they won't even be displayed back to you so they are only usefull for filtering purposes.

## Advanced usage : 

### Using specific notebooks (folders)

Taskwarrior-JP can create todo-notes in a specific notebook (also called folder) and is also able to move finished todo to a specific notebook (also called folder).
If you intend to use any of these options (which I strongly suggest, at least for the creation) you can call `./tjp.py --list-notebooks`.
This will display a list of your current notebooks and their ID.
You can use these IDs in your `tjp.ini`.

As a personal preference, I have a notebook called "TODO" in Joplin, which has 2 sub-notebooks : "todo" and "done".
I configured my Taskwarrior-JP to :
 * read only from the "TODO>todo" notebook (option "folder_todo").
 * create in this same notebook (option "folder_add").
 * move completed tasks to the "TODO>done" notebook (option "folder_done").

But do as you please. 

### Reading and writing long texts

A feature that Taswarrior was missing, IMHO, was the ability to write down "long" notes.
There was an "annotate" feature, but it was limited to short text.
Thanks to Joplin's way of handling todo-notes (which are actual notes :) !), it is possible to write texts as long as you desire !
To write notes for todo-note of ID 8 : `./tjp.py 8 edit`.
You can also read the "Raw access" part of this README and simply use Joplin to add as many texts/pictures/whatever you want to your notes.

By default, Taskwarrior-JP will use the editor in your "EDITOR" environment variable (and defaults to `vim`).

If you don't want to start a full-featured editor and only read your note in your terminal : `./tjp.py 8 cat`.

### Dependencies

A powerful feature of Taskwarrior is its capacity to handle dependencies.
Taskwarrior-JP is also capable of doing that :)

Example : 
 * task of id "987" is "Eating meal"
 * task of id "123" if "Cooking meal"
 * You can specify that task 987 depends on task 123 this way : `./tjp.py 987 modify depends:123`

You can specify multiple dependencies by using commas. Example :
 * task "456" is "Sit at the dining table"
 * `./tjp.py 987 modify depends:123,456` now makes "Eating meal" dependent on both "Cooking meal" and "Sit at the dining table".

Tasks that are currently blocking others are prioritised higher.

Tasks that are currently blocked by others are prioritised lower.

### Raw access

As previously stated, Taskwarrior-JP is only a script to manipulate Joplin's todo-notes.
Taskwarrior-JP does not store anything by itself.
Everything is stored in Joplin.
Taskwarrior-JP's tag and metadata are therefore stored within Joplin's note themselves.
You can see (and modify) everything from within your Joplin app.
If you know [Pelican](https://github.com/getpelican/pelican), the format will be familiar :)

In a nutshell : notes start with "key:value" lines, then an empty line, then the "raw" body (what you access with `./tjp.py XXX cat` and `./tjp.py XXX edit`).

You can modify the notes directly in Joplin without any problem (actually, I often do it from the mobile app) as long as you respect that syntax.

### Arguments order

The man of the real Taskwarrior shows this format : `task <filter> <command> [ <mods> | <args> ]`.
Taskwarrior-JP accepts the same format and knows the following commands :
 * `next` (which is the default one if no command is written) : displays the tasks you selected with you filters. The most urgent tasks are first.
 * `add` : creates a new task (using your specified "mods" and "args", the title being the default arg).
 * `done` : mark as "done" the single task selected by your filter (the most often used filter being the ID of a note).
 * `modify` : select a single task thanks to your filter and modify it according to your mods and args.
 * `cat` : displays the content of the body of the single task selected by your filters.
 * `edit` : opens a text editor for you to view/edit the body of the single task selected by your filters.

Filters can be specified in any order. So can be mods and args.

So, all these way of specifying mods/args are equivalents :
 * `./tjp.py add +work +boss due:tomorrow "Write a mail."`
 * `./tjp.py add +work "Write a mail." due:tomorrow +boss`
 * `./tjp.py add "Write a mail." due:tomorrow +work +boss`

And all these way of filtering are equivalents :

 * `./tjp.py +work 3 -priority:L cat`
 * `./tjp.py +work -priority:L 3 cat`
 * `./tjp.py 3 -priority:L +work cat`

The same thing applies for modifying. All these lines are the same :

 * `./tjp.py +work 3 -priority:L modify due:tomorrow depends:0cc`
 * `./tjp.py 3 +work -priority:L modify depends:0cc due:tomorrow`
 * `./tjp.py -priority:L +work 3 modify depends:0cc due:tomorrow`

### Dates

Taskwarrior has a super powerful way of handling dates.
Taskwarrior-JP has not :)

The only special dates that Taskwarrior-JP understands are "today" and "tomorrow".

Ex : `./tjp.py add "Testing TJP" due:today`

As already stated, all other dates (or times) must be formated "YYYY-MM-DD" (or "YYYY-MM-DD HH:mm").

### Small word about IDs

Each note in Joplin has a unique ID which looks like that : 0cc175b9c0f1b6a831c399e269772661

I believe that this would be too long to type (and to display) in a CLI.
Therefore, Taskwarrior-JP computes the shortest summary of these IDs that are unambiguous.
These short versions are the IDs that are displayed to you in the "ID" column.

The trick is that Taskwarrior-JP computes the shortest unambiguous ID **among the selected notes** (not among all the notes that exist within your Joplin).
So, if you ask to list work-tagged lists (`./tjp.py +work`), see the one you want with ID "3", and try to modify it with `./tjp.py 3 modify ...` you MAY encounter an error.

Indeed, "3" was the shortest unambiguous ID among tasks tagged with the "work" tag but there might be another task with an ID starting with "3" that is not work-tagged.
So, if you want to be sure that your `modify` will work, you need keep the same filters you had when displaying your tasks.
In this example, you'd have to type : `./tjp.py +work 3 modify ...`.

Don't worry : if you use an ambiguous ID, Taskwarrior-JP won't perform any modification, will warn you, and will show you the ambiguous tasks (alongside with unambiguous IDs for them :)).

Now that you know everythinh about IDs, this last tip won't surprise you : by default, Taskwarrior-JP uses colored output.
The fields within the ID columns can use two colors.
The shortest unambiguous ID is highlighted and, if there's still room within the cell, Taskwarrior-JP will write the next few characters of the note's ID (even though they are "useless").
Everytime you use an ID to select/filter a todo-note, you can use the shortest form or any longer form.

Example : If Joplin's id of a todo-note is 0cc175b9c0f1b6a831c399e269772661, and its unambiguous ID (displayed by Taskwarrior-JP) is "0c", then you can use either "0c", "0cc", "0cc1", "0cc17", etc.
All these ways of refering to this task are equivalent for Taskwarrior-JP.
It means that : `./tjp.py 0c done` is the same as `./tjp.py 0cc175b done` (the short one is only slightly more ambiguous).
