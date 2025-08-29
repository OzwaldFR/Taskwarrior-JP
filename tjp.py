#!/usr/bin/env python


# ROADMAP :
# - "waiting" tasks (simplified version of "scheduled & stuff")
# - re-write the whole display (title as the last colums, better fitting, ...)


import urllib.request
import configparser
import tempfile
import datetime
import logging
import json
import time
import sys
import os
import re

import prettytable


logger = logging.getLogger(__name__)


# =============================================================================
#                           A todo-Note object
# =============================================================================


class TodoNote:
    JOPLIN_PROPERTIES = ('id', 'parent_id', 'title', 'body', 'created_time',
                         'updated_time', 'is_conflict', 'latitude', 'longitude',
                         'altitude', 'author', 'source_url', 'is_todo',
                         'todo_due', 'todo_completed', 'source',
                         'source_application', 'application_data', 'order',
                         'user_created_time', 'user_updated_time',
                         'encryption_cipher_text', 'encryption_applied',
                         'markup_language', 'is_shared', 'shared_id', 
                         'conflict_original_id', 'master_key_id', 'user_data',
                         'deleted_time', 'body_html', 'base_url',
                         'image_data_url', 'crop_rect',)


    def __init__(self, joplin_json=None):
        self.metadata = {}
        self.body_text = ''
        self.title = ''

        if joplin_json:
            self.load_joplinjson(joplin_json)


    def load_joplinjson(self, joplin_json):
        """Load a JSON from Joplin into a TodoNote Python object."""
        for key,value in joplin_json.items():
            setattr(self, key, value)
        # Parsing body = metadata + body_text
        body = self.body if hasattr(self, 'body') else ''

        metadata = {}
        for i,line in enumerate(body.split('\n')):
            if not ':' in line:
                if line.strip()=='':
                    break  # We parsed all the metadata (empty line encountered)
                else:
                    # That line is not empty, nor metadata.
                    # Therefore, the body is either malformed or what we
                    # encountered before was actually not metadata.
                    metadata = {}
                    break
            else:
                key,value = line.split(':', 1)
                if key in metadata:  # Multiline metadata (Pelican's way of doing it)
                    metadata[key] += '\n'+value
                else:
                    metadata[key] = value
    
        if metadata=={}:  # Actually no metadata was read. Rewinding :)
            i=-1

        if i+1<len(body.split('\n')):
            self.body_text = '\n'.join(body.split('\n')[i+1:])
        else:
            self.body_text = ''

        # Casting some metadata to Python objects.
        updated_metadata = {}
        for key, value in metadata.items():
            updated_metadata[key] = self._metadata_txt2python(key, value)
        metadata.update(updated_metadata)
        if 'id' in joplin_json:
            metadata['id'] = joplin_json['id']

        self.metadata = metadata


    def to_joplinjson(self):
        """Dumps this TodoNote into a Joplin-compatible json."""
        result = {}
        for attribute in TodoNote.JOPLIN_PROPERTIES:
            if hasattr(self, attribute):
                result[attribute] = getattr(self, attribute)

        body = ''
        for key in sorted(self.metadata.keys()):
            value = self._metadata_python2txt(key, self.metadata[key])
            if value:
                body += '%s:%s\n'%(key, value)

        body += '\n'+self.body_text
        # TODO bonus : add "todo_due" joplin attribute and stuff ?
        result['body'] = body

        result['is_todo'] = 1
        return result


    def __repr__(self):
        return json.dumps(self.to_joplinjson())


    def __str__(self):
        return getattr(self, 'title', '') or self.__repr__()


    @property
    def urgency(self):
        # Inspiration : https://taskwarrior.org/docs/urgency/
        result = 0
        if getattr(self, "todo_completed", 0)!=0:
            # Already completed have the lowest urgency.
            # Between them, they are discrimated by newest first.
            result = -100
            result += getattr(self, "updated_time", 0)/(10**(10+3))
            
        if "next" in self.metadata:
            result += 15
        if "due" in self.metadata:  # Max : +12
            result += 4
            due = self.metadata['due']
            if hasattr(self.metadata['due'], 'date'):  # Actually datetime.datetime
                due = due.date()
            days_left = due - datetime.date.today()
            if days_left.days <= 1:
                result += 8
            else:
                result += 8/round(1+days_left.days/7, 1)
        if "priority" in self.metadata:
            result += {'H':6, 'M':3.9, 'L':1.8}.get(self.metadata["priority"],0)
        if "tags" in self.metadata:
            result += 1
        if getattr(self, 'BLOCKED', False) is True:
            result -= 5
        if getattr(self, 'BLOCKING', False) is True:
            result += 8
        return result


    @staticmethod
    def _metadata_txt2python(key, value):
        if key=='tags':
            value = [tag.strip() for tag in value.split(',')]
            if '' in value:
                value.remove('')
        elif key=='depends':
            value = [uid.strip() for uid in value.split(',')]
            if '' in value:
                value.remove('')
        elif key in ('due',):
            value = value.strip()
            date_regex = '[12][0-9]{3}-[01][0-9]-[0-3][0-9]'
            if re.match(date_regex + ' [0-2][0-9]:[0-5][0-9]', value):
                value = datetime.datetime.fromisoformat(value)
            elif re.match(date_regex, value):
                value = datetime.date.fromisoformat(value)
            elif value=='today':
                value = datetime.date.today()
            elif value=='tomorrow':
                value = datetime.date.today() + datetime.timedelta(days=1)
            elif value=='':  # Deleting metadata
                value = None
            else:
                raise ValueError('Bad "due" attribute. Not valid fmt : %s'%(value))
        return value


    @staticmethod
    def _metadata_python2txt(key, value):
        if key=='tags':
            value = ', '.join([tag for tag in value])
        elif key=='depends':
            value = ', '.join([uid for uid in value])
        elif isinstance(value, datetime.datetime):
            value = value.strftime('%Y-%m-%d %H:%M')
        elif isinstance(value, datetime.date):
            value = value.strftime('%Y-%m-%d')

        return value
        

# =============================================================================
#                           The main object
# =============================================================================


class Joplin:
    """This object has these main function families :
    - retrieving notes
    - filtering notes
    - displaying notes
    - sorting notes
    - modifying/saving notes
    """

    def __init__(self, args):
        # Parsing/Saving args
        if getattr(args, 'config'):
            if not os.path.isfile(args.config):
                logger.error('No such config file : %s'%args.config)
            else:
                config = configparser.ConfigParser()
                config.read(args.config)
        
                for key,value in config['global'].items():
                    logger.debug('Config file %s = %s'%(key, value))
                    setattr(self, key, value)

        if getattr(args, 'token', None)!=None:
            self.token = args.token
        if not getattr(self, "token", None):
            raise ValueError('You need to configure the Joplin WebClipper Token.')

        if getattr(args, 'url', None) != None:
            self.url = args.url
        if not getattr(self, "url", False):
            self.url = 'http://127.0.0.1:41184'  # Default handling should be improved

        self.color = None
        if getattr(args, 'color', None):
            self.color = True
        if getattr(args, 'no_color', None):
            self.color = False
        if self.color is None:
            self.color = sys.stdout.isatty() and ('color' in os.environ.get('TERM',''))


        if getattr(args, 'display_all', None):
            self.display_all = args.display_all
        if getattr(args, 'display_really_all', None):
            print('args.display_really_all : %s'%str(args.display_really_all))
            self.display_really_all = args.display_really_all
        
        # keys = note id. Values = TodoNote instance (WARNING : most might not have
        # their metadata parsed)
        self.CACHE = {}


    # Utils ===================================================================


    def list_notebooks(self):
        url = self.url + '/folders?'
        #url += 'order_by=updated_time&order_dir=ASC'
        url += 'fields=id,parent_id,title'
        url += '&token='+self.token
        f = urllib.request.urlopen(url)
        data = json.loads(f.read().decode('utf-8'))  # TODO : pagination
        # My version of Joplin (3.0.13) does not returns the "children" attr.
        # So...I have to re-implement it (in a quick & VERY dirty way :-D)

        msg = 'Here are your notebooks (ID and Title)'
        print(msg+'\n'+('='*len(msg)))
        def recur_print(items, parent_id='', ident=''):
            for item in items:
                if item['parent_id']==parent_id:
                    print(ident+item['id']+' ('+item['title']+')')
                    recur_print(items, item['id'], ident+'  ')

        recur_print(data['items'])


    # Retrieving notes ========================================================


    def get_todos(self, finished=None, really_all=None, all_=None, completed=None):
        # If 'finished' is False, will discard finished todo.
        # If 'finished' is True, will return both finished and unfinished todos.
        # If 'finished' is None, its value will be computed from the other options.
        #
        # There are what I might want to fetch :
        # --really-all : 
        #     * no parent_id filering
        #     * not discarding completed tasks
        # --all :
        #     * parent_id = "folder_todo" + "folder_done" + "folder_add"
        #                    or no parent_id filtering if these options
        #                    are not defined.
        #     * not discarding completed tasks
        # --completed :
        #     * parent_id = "folder_done" (or no filtering if option undefined)
        #     * discarding uncompleted tasks
        # --to-be-done (default) : 
        #     * parent_id = "folder_todo" (or no filtering if option undefined)
        #     * discarding completed tasks

        if really_all is None:
            really_all = getattr(self, 'display_really_all', None)
        if all_ is None:
            all_ = getattr(self, 'display_all', None)
        if completed is None:
            completed = getattr(self, "completed", None)

        folders_to_request = set()
        fetch_root = False
        if really_all:
            fetch_root = True
            if finished is None:
                finished = True
        elif all_:
            for folder in ('folder_todo', 'folder_done', 'folder_add'):
                if getattr(self, folder, False):
                    folders_to_request.add(getattr(self, folder))
            if finished is None:
                finished = True
        elif completed:
            finished = True
            if getattr(self, 'folder_done', False):
                folders_to_request.add(self.folder_done)
            else:
                fetch_root = True
        else:  # Default : only display what is still to be done.
            if getattr(self, 'folder_todo', False):
                folders_to_request.add(self.folder_todo)
            else:
                fetch_root = True

        if len(folders_to_request)==0:
            fetch_root = True

        logger.debug('Really_all=%s  All=%s  Completed=%s  Finished=%s'%(
                    really_all, all_, completed, finished))

        logger.debug('Fetching TODOs from folders : %s'%str(folders_to_request))

        # curl 'http://localhost:41184/notes?order_by=updated_time&order_dir=ASC&token=TOKENVALUE'|jq .|less
        result = []
        while True:
            url = self.url
            if not fetch_root:
                try:
                    parent_id = folders_to_request.pop()
                except KeyError:  # Empty set
                    return result
                url += '/folders/%s'%parent_id
            else:
                fetch_root = False  # Only fetching the root once.
                
            base_url = url
            page = 1
            while not (page is False):
                url = base_url + '/notes?'
                url += 'order_by=updated_time&order_dir=ASC'
                url += '&fields=id,parent_id,is_todo,title,todo_completed,updated_time'
                url += '&token='+self.token
                url += '&page='+str(page)
                logger.debug('Fetching page %s (%s)'%(page, url))
                try:
                    f = urllib.request.urlopen(url)
                except urllib.error.URLError as err:
                    logger.critical('Failed to connect to Joplin (%s). '
                                    ' Is the webclipper running at %s ?'%(
                                    str(err), self.url))
                    sys.exit(1)
                data = json.loads(f.read().decode('utf-8'))
                if data['has_more']:
                    page += 1
                else:
                    page = False

                for item in data['items']:
                    if item['is_todo']!=0:
                        if (finished is True) or (item['todo_completed']==0):
                            if not "body" in item:
                                url = self.url+'/notes/%s'%item['id']
                                url += '?fields=body&token='+self.token

                                f = urllib.request.urlopen(url)
                                data = json.loads(f.read().decode('utf-8'))
                                item.update(data)

                            new_note = TodoNote(item)
                            result.append(new_note)
                            self.CACHE[item['id']] = new_note
                        else:
                            self.CACHE[item['id']] = TodoNote(item)


    # Compute automatic tags (overdue, blocked, blocking, ...)=================
    
    
    def compute_auto_tags(self, todos):
        logger.debug('Auto tagging : %s'%(', '.join([t.id for t in todos])))
        # === OVERDUE ===
        # NB : this attribute is not used yet. Will most likely be within print.
        finished = set()
        not_finished = set()
        for todo in todos:
            todo.OVERDUE = False
            if todo.metadata.get('due'):
                due = todo.metadata.get('due')
                now = datetime.date.today() 
                if isinstance(due, datetime.datetime):
                    now = datetime.datetime.now()  # Cannot compare datetime to date
                todo.OVERDUE = due < now
            if todo.todo_completed == 0:
                not_finished.add(todo.id)
            else:
                finished.add(todo.id)

        # === BLOCKED ===
        depends_all = set()
        for todo in todos:
            todo.BLOCKED = False
            if todo.todo_completed:
                continue  # Cannot be blocked, nor blocking

            depends = todo.metadata.get('depends',[])
            BLOCKED = False
            for dependency in depends:
                depends_all.add(dependency)
                if dependency in not_finished:
                    BLOCKED = True
                    # Do not "break" here otherwise we screw "depends_all"
            todo.BLOCKED = BLOCKED

        # === BLOCKING ===
        for todo in todos:
            todo.BLOCKING = False
            if todo.todo_completed:
                continue  # Cannot be blocking
            if todo.id in depends_all:
                todo.BLOCKING = True


    # Filter Notes ============================================================


    def filter_todos(self, filters, todos):
        # Special case : if we have no filters, we return "todos" immediately.
        if len(filters)==0:
            logger.debug('No filters passed.')
            result = todos
            self.compute_localid(result)
            return result
        
        # We have at least one filter, we keep only the notes that match ALL
        # of them.
        # First step : creating our list of filters as a list of python func.
        filter_functions = []

        # Having more then 1 ID filter make no sense and is most likely a
        # usage error. So we will refuse to obey in such case.
        allow_id_filter = True
        
        for filter_text in filters:
            if ':' in filter_text:
                logger.debug('Filter : metadata "%s"'%filter_text)
                filter_function = ('_filter_metadata', {'filter_text':filter_text})
                filter_functions.append(filter_function)
            elif allow_id_filter and re.match('^[0-9a-f]+$', filter_text):
                logger.debug('Filter : id starts with %s'%filter_text)
                filter_function = ("_filter_id", {"filter_id":filter_text})
                filter_functions.append(filter_function)
                allow_id_filter = False
            elif filter_text[0] in '+-':  # This is a tag filter
                logger.debug('Filter : tag "%s" %spresent.'%(
                        filter_text[1:],
                        'not ' if filter_text[0]=='-' else '',
                     ))

                filter_function = ('_filter_tag', {
                                    'tag':filter_text[1:],
                                    'negative':filter_text[0]=='-',
                                  })

                filter_functions.append(filter_function)
            else:  # Text filter.
                # For now we only search the titles and are not case-sensitive.
                # Maybe we should expand to body_text ? Or restrict to be case-
                # sensitive ? We'll see how things goes while we use it.
                logger.debug("Filter : text search > %s"%filter_text)
                filter_function = ('_filter_text', {'filter_text':filter_text})
                filter_functions.append(filter_function)
        
        # Now we apply the filters
        result = []
        for todo in todos:
            add_me = True
            for filter_name,filter_args in filter_functions:
                if not(getattr(self, filter_name)(todo,**filter_args)):
                    add_me = False
                    break
            if add_me is True:
                result.append(todo)

        self.compute_localid(result)
        return result


    @staticmethod
    def _filter_tag(todo, tag, negative=False):
        if not negative:
            return (tag in todo.metadata.get('tags',[]))
        return not (tag in todo.metadata.get('tags',[]))


    @staticmethod
    def _filter_id(todo, filter_id):
        if len(filter_id)<1:
            raise ValueError('Cannot filter on an empty ID.')
        return todo.id.startswith(filter_id)


    @staticmethod
    def _filter_text(todo, filter_text):
        if len(filter_text)<1:
            raise ValueError('Cannot filter on empty text.')
        return filter_text.lower() in todo.title.lower()


    @staticmethod
    def _filter_metadata(todo, filter_text):
        """Special case : if "filter_value" is empty, this filter means :
        - True if the attribute is not defined, False otherwise
        (obviously, if there is a minus sign, it's reversed)
        """
        negative = False
        if filter_text.startswith('-'):
            negative = True
            filter_text = filter_text[1:]

        filter_key, filter_value = filter_text.split(':',1)

        if not filter_key in todo.metadata:
            if negative is False:
                return filter_value.strip()==''
            else:
                return filter_value.strip()!=''

        result = filter_value == todo.metadata[filter_key]
        if negative is True:
            return not result
        return result


    # Printing notes ==========================================================


    @staticmethod
    def _strip_colors(string):
        regex = '\033\[[0-9]+m'
        while string!=re.sub(regex, '', string):
            string = re.sub(regex, '', string)
        return string


    def _fmt4cell(self, value, compression_level=0, key=None):
        """Called to transform some TodoNote attribute (or metadata) to a string
        that will be displayed in a cell"""
        if isinstance(value, float):
            return '%.01f'%value
        elif value is True:
            return 'T'
        elif value is False:
            colors = {True:('\033[2m','\033[0m'),False:('','')}[self.color]
            return colors[0]+'F'+colors[1]
        elif isinstance(value, list):
            return ' '.join([self._fmt4cell(E) for E in value])
        elif isinstance(value, datetime.datetime):
            return value.strftime('%Y-%m-%d %H:%M')
        elif isinstance(value, datetime.date):
            return value.strftime('%Y-%m-%d')

        return value


    def compute_localid(self, todos):
        """Takes a list of "TODOs" and compute, for each of them, the shortest
        start of their "id" attribute that is unique.
        This shortest id is saved as "localid" attribute (only in memory)
        """
        logger.debug('Computing local ids.')
        todos.sort(key=lambda td:td.id)
        for i, todo in enumerate(todos):
            previous_uniq_len = 0
            uniq_len = 1
            while previous_uniq_len != uniq_len:
                previous_uniq_len = uniq_len
                if i>0 and todos[i-1].id[:uniq_len] == todo.id[:uniq_len]:
                    uniq_len += 1
                elif i+1<len(todos) and todos[i+1].id[:uniq_len] == todo.id[:uniq_len]:
                    uniq_len += 1
            todo.localid = todo.id[:uniq_len]
            logger.debug('Computed local ID %s : %s'%(todo.id ,todo.localid))


    def generate_table(self, todos, max_width=9999, compression_level=0):
        """
        `compression_level` can be increased by recursive calls to fit `max_width`.
        """
        if len(todos)==0:
            print('Nothing to display.')
            return

        todos.sort(key=lambda T:T.urgency, reverse=True)

        table = prettytable.PrettyTable()

        table.border = False
        table.preserve_internal_border = True
        table.padding_width = 0
        table.set_style(prettytable.SINGLE_BORDER)

        # === Generating the widest table.

        COLUMNS = [('id', 'ID'),('title','title'), ('age', 'Age'), ('priority', 'P'),
                   ('project', 'Proj'), ('tags', 'Tag'), ('due', 'Due'),
                   ('urgency', 'Urg'),('depends', 'Dep'),
                   ('BLOCKED','Blkd'), ('BLOCKING', 'Blkg' )]

        getid = lambda td:getattr(td,'localid',getattr(td,'id','???'))

        for key,label in COLUMNS:
            if key=='id':
                widest_localid = max([len(getid(t)) for t in todos])
                column = []
                for todo in todos:
                    seps = ['\033[96m', '\033[0m\033[2m', '\033[0m']
                    if not self.color:
                        seps = ['',' ','']
                    cell = seps[0] + getid(todo) + seps[1]
                    cell+= getattr(todo,'id','???')[len(self._strip_colors(cell)):widest_localid]
                    cell+= seps[2]
                    column.append(cell)
                table.add_column(label, column)
            elif key=='age':
                pass  # TODO
            elif [key in todo.metadata for todo in todos].count(True)>0:
                if key=='depends':
                    column = []
                    for todo in todos:
                        localids = []
                        for id_ in todo.metadata.get(key,[]):
                            if id_ in self.CACHE:
                                localids.append(getattr(self.CACHE[id_], 'localid', id_[:4]+'…'))
                            else:
                                localids.append(id_[:4]+'?')
                        column.append(' '.join(localids))
                    table.add_column(label, column)
                elif key=='due':
                    column = []
                    seps = {True:('\033[91m', '\033[0m'), False:('','')}[self.color]
                    for todo in todos:
                        if getattr(todo, 'OVERDUE', False):
                            column.append(seps[0]+self._fmt4cell(todo.metadata['due'])+seps[1])
                        else:
                            column.append(self._fmt4cell(todo.metadata.get('due','')))
                    table.add_column(label, column)
                else:
                    table.add_column(
                        label,
                        [
                            self._fmt4cell(t.metadata.get(key,'')) for t in todos
                        ])
            elif key=="title":
                seps = {True:('\033[2m', '\033[0m'), False:('<F>','</F>')}[self.color]
                column = []
                for todo in todos:
                    text = self._fmt4cell(todo.title)
                    if getattr(todo,'todo_completed',0) != 0:
                        text = seps[0]+text+seps[1]
                    for key,value in todo.metadata.items():
                        annotation_seps = {True:('\033[0m\033[2m','\033[0m'),False:('','')}[self.color]
                        if key.startswith('annotation_'):
                            moment = datetime.datetime.fromisoformat(key[11:])
                            text += '\n %s:%s'%(
                                annotation_seps[0]+self._fmt4cell(moment)+annotation_seps[1], value)
                            
                    column.append(text)
                table.add_column(label, column)
            elif [hasattr(todo,key) for todo in todos].count(True)>0:
                table.add_column(
                    label,
                    [
                        self._fmt4cell(getattr(t, key)) for t in todos
                    ])

        table.align['title'] = 'l'  # Must apply style after adding the column.
        table.align['ID'] = 'l'  # Must apply style after adding the column.

        # === Shrinking the table if needed 

        table_str = str(table)
        try:
            avail_width = max(os.get_terminal_size().columns, 60)
        except OSError:  # Most likely not a tty
            avail_width = 999666

        current_width = max([len(self._strip_colors(L)) for L in table_str.split('\n')])
        removable_columns = ['Blkg', 'Blkd', 'Urg']
        while current_width > avail_width:
            #logger.debug('Table too wide (%d > %d)!'%(current_width, avail_width))
            removed_a_column = False
            for removable in removable_columns:
                if removable in table.field_names:
                    table.del_column(removable)
                    removed_a_column = True
                    break

            if removed_a_column:
                table_str = str(table)
                current_width = max([len(self._strip_colors(L)) for L in table_str.split('\n')])
                if current_width <= avail_width:
                    break

            # If I reach this line, I already have removed every possible columns
            # but it's not enough.
            if not 'title' in table._max_width:
                table._max_width['title'] = avail_width//2
                table._max_width['Tag'] = avail_width//4
            else:
                table._max_width['title'] = table._max_width['title']-1
                table._max_width['Tag'] = max(6, table._max_width['Tag']-1)

            table_str = str(table)
            current_width = max([len(self._strip_colors(L)) for L in table_str.split('\n')])
                
        print(table)


    # Commands ================================================================


    def do_next(self, filters, mods_args):
        todos = self.get_todos()
        self.compute_auto_tags(todos)
        filtered_todos = self.filter_todos(filters, todos)
        self.generate_table(filtered_todos)


    def do_done(self, filters, mods_args):
        todos = self.get_todos()
        filtered_todos = self.filter_todos(filters, todos)
        if len(filtered_todos) > 1:
            logger.critical('FATAL:ambiguous selection. "Done" must be called on a single item.')
            self.generate_table(filtered_todos)
        elif len(filtered_todos) < 1:
            logger.critical('FATAL:no todo matches your filter.')
        else:
            todo = filtered_todos[0]
            DATA = {'todo_completed':int(time.time()*1000)}
            if getattr(self, "folder_done", False):
                logger.debug('Will move to notebook %s'%(self.folder_done))
                DATA['parent_id'] = self.folder_done
            DATA = json.dumps(DATA)

            req = urllib.request.Request(
                        url=self.url+'/notes/'+todo.id+'?token='+self.token,
                        data=DATA.encode('utf-8'),
                        method='PUT',
                        )
            logger.debug('Will mark TODO %s as completed.'%todo.id)
            with urllib.request.urlopen(req) as f:
                pass
            print('Task finished : %s'%todo.title)
                

    def do_annotate(self, filters, mods_args):
        todos = self.get_todos()
        filtered_todos = self.filter_todos(filters, todos)
        if len(filtered_todos) > 1:
            logger.critical('FATAL:ambiguous selection. "Annotate" must be called on a single item.')
            self.generate_table(filtered_todos)
            return
        elif len(filtered_todos) < 1:
            logger.critical('FATAL:no todo matches your filter.')
            return
        todo = filtered_todos[0]

        annotation = ' '.join(mods_args)
        annotation = annotation.lstrip().rstrip()
        if annotation=='':
            print('Empty annotation is ignored.')
            return

        key = 'annotation_'
        moment = datetime.datetime.now().isoformat().replace('-','').replace(':','')
        key += moment

        todo.metadata[key] = annotation

        todo_json = todo.to_joplinjson()

        DATA = {'body':todo_json['body']}
        # TODO : update modified time & co.
        DATA = json.dumps(DATA)
        req = urllib.request.Request(
                    url=self.url+'/notes/'+todo.id+'?token='+self.token,
                    data=DATA.encode('utf-8'),
                    method='PUT',
                    )
        logger.debug('Annotating TODO of ID:%s'%todo.id)
        with urllib.request.urlopen(req) as f:
            pass
    

    def do_edit(self, filters, mods_args):
        """This feature does not exist in Taswarrior. This opens EDITOR and
        allows you to edit "body_text" (reminder : body=metadata+body_text """
        todos = self.get_todos()
        filtered_todos = self.filter_todos(filters, todos)
        if len(filtered_todos) > 1:
            logger.critical('FATAL:ambiguous selection. "Edit" must be called on a single item.')
            self.generate_table(filtered_todos)
            return
        elif len(filtered_todos) < 1:
            logger.critical('FATAL:no todo matches your filter.')
            return

        todo = filtered_todos[0]

        editor = getattr(self, 'editor', os.environ.get('EDITOR', 'vim'))
        edited_file = tempfile.NamedTemporaryFile()
        edited_file.write(todo.body_text.encode('utf-8'))
        edited_file.flush()
        cmd = [editor, edited_file.name]
        logger.debug(str(cmd))
        os.system(' '.join(cmd))  # TODO : make it cleaner
        edited_file.seek(0)
        new_content = edited_file.read().decode('utf-8')

        logger.debug('Original len : %d'%len(todo.body_text))
        logger.debug('Edited len   : %d'%len(new_content))
        logger.debug('Modified     : %s'%(todo.body_text != new_content))

        if todo.body_text == new_content:
            logger.info('No modification.')
            return

        todo.body_text = new_content
        todo_json = todo.to_joplinjson()
        
        DATA = {'body':todo_json['body']}
        # TODO : update modified time & co.
        DATA = json.dumps(DATA)

        req = urllib.request.Request(
                    url=self.url+'/notes/'+todo.id+'?token='+self.token,
                    data=DATA.encode('utf-8'),
                    method='PUT',
                    )
        logger.debug('Will update the text of %s.'%todo.id)
        with urllib.request.urlopen(req) as f:
            pass
    

    def do_add(self, filters, mods_args):
        if len(filters)!=0:
            raise ValueError('The "add" verb must be first.')
        if len(mods_args)==0:
            raise ValueError('Cannot call "add" alone. At least add a title.')

        title, tags, metadata = self._parse_mods_args(mods_args)

        data = TodoNote()
        data.title = title
        data.metadata = metadata
        data.metadata['tags'] = [tag[1:] for tag in tags]  # Removing the "+"
        if 'due' in data.metadata:
            # Transforming to Python datetime, mandatory to compute urgency,
            # which itself is mandatory to be able to print this TodoNote.
            data.metadata['due'] = data._metadata_txt2python('due', data.metadata['due'])
        # "Depends" hook
        if "depends" in data.metadata:
            self._expand_depends_id(data)
        self.generate_table([data])
        data = data.to_joplinjson()

        
        if getattr(self, 'folder_add', False):
            data.update({'parent_id':self.folder_add})
        else:
            logger.warning('WARNING : no notebook id configured as "folder_add". '+
                  'Creating the todo within joplin\'s root.')
        logger.debug('Sending to Joplin : %s'%str(data))
        
        req = urllib.request.Request(
                    url=self.url+'/notes?token='+self.token,
                    data=json.dumps(data).encode('utf-8'),
                    method='POST',
                    )
        
        with urllib.request.urlopen(req) as f:
            pass


    def do_cat(self, filters, mods_args):
        """This feature does not exist in Taswarrior. This display on stdout
        the "body_text" of a task (reminder : body=metadata+body_text) """
        todos = self.get_todos()
        filtered_todos = self.filter_todos(filters, todos)
        if len(filtered_todos) > 1:
            logger.critical('FATAL:ambiguous selection. "Cat" must be called on a single item.')
            self.generate_table(filtered_todos)
            return
        elif len(filtered_todos) < 1:
            logger.critical('FATAL:no todo matches your filter.')
            return

        todo = filtered_todos[0]
        print(todo.body_text)


    def do_modify(self, filters, mods_args):
        todos = self.get_todos()
        filtered_todos = self.filter_todos(filters, todos)
        if len(filtered_todos) > 1:
            logger.critical('FATAL:ambiguous selection. "Modify" must be called on a single item.')
            self.generate_table(filtered_todos)
            return
        elif len(filtered_todos) < 1:
            logger.critical('FATAL:no todo matches your filter.')
            return
        elif len(mods_args) == 0:
            logger.critical('FATAL:you asked no modification. Doing nothing.')
            return

        todo = filtered_todos[0]
        title, tags, metadata = self._parse_mods_args(mods_args)

        DATA = {}
        logger.debug('You asked to modify "%s" (%s) :'%(todo.title, todo.id))
        if tags:
            for tag in tags:
                if (tag[0]=='-') and (tag[1:] in todo.metadata.get('tags',[])):
                    todo.metadata['tags'].remove(tag[1:])
                    DATA['body'] = todo.to_joplinjson()['body']
                elif tag[0]=='+' and not (tag[1:] in todo.metadata.get('tags',[])):
                    todo.metadata['tags'] = todo.metadata.get('tags',[])+ [tag[1:]]
                    DATA['body'] = todo.to_joplinjson()['body']
            logger.debug('Tags : %s'%str(tags))
        if metadata:
            logger.debug('Metadata : %s'%(
                 '\n'.join(['%s:%s'%(key,value) for key,value in metadata.items()])))
            for key,value in metadata.items():
                todo.metadata[key] = TodoNote._metadata_txt2python(key, value)

            if "depends" in metadata:
                self._expand_depends_id(todo, todos)
            
            DATA['body'] = todo.to_joplinjson()['body']

        if title:
            logger.debug('Title : %s'%str(title))
            todo.title = title  # Only usefull for the summary print @end of func.
            DATA['title'] = title

        logger.debug('I shall PUT this : \n',DATA)

        DATA = json.dumps(DATA)

        req = urllib.request.Request(
                    url=self.url+'/notes/'+todo.id+'?token='+self.token,
                    data=DATA.encode('utf-8'),
                    method='PUT',
                    )
        logger.debug('Will modify TODO %s.'%todo.id)
        with urllib.request.urlopen(req) as f:
            pass

        self.generate_table([todo])


    def _parse_mods_args(self, mods_args):
        # Parsing mods_args following these rules :
        # * arg starting with "+" or '-' is a tag
        # * arg matching '[a-z]+:' is a metadata
        # * every other args are part of the title.
        title = []
        metadata = {}
        tags = []

        for i,chunk in enumerate(mods_args):
            if re.match('^[+-][a-zA-Z0-9]', chunk):
                tags.append(chunk)
            elif re.match('^[a-zA-Z]+:[^ ]*', chunk):
                key,value = chunk.split(':',1)
                metadata[key] = value
            else:
                title.append(chunk)

        title = ' '.join(title)
        logger.debug('Title : %s'%str(title))
        logger.debug('Tags : %s'%str(tags))
        logger.debug('Metadata : %s'%str(metadata))
        return title, tags, metadata

    
    def _expand_depends_id(self, todo, todos=None):
        """Takes a TodoNote with a "depends" metadata populated with localid
        Plus a potentiel "todos" list of TodoNote.
        Check that every localid within the "depends" list belongs to a single
        TodoNote and replace the localid by the full id. If not, raiseValueError.
        """
        if not "depends" in todo.metadata:
            return

        if todos is None:
            # Should I allow finished TODOs also ? That would be more "feature
            # complete" but I really do not feel like doing it because that
            # would make the code slower and more complex...Maybe just as a
            # fallback in case I find zero ongoing task with a specific localid?
            todos = self.get_todos()

        self.compute_localid(todos)  # Just in case.
        
        result = []
        for localid in todo.metadata['depends']:
            valid = [todo_ for todo_ in todos if todo_.id.startswith(localid)]
            if len(valid)==1:
                result.append(valid[0].id)
                continue
            elif len(valid)==0:
                raise ValueError('Could not find any task with ID matching %s'%localid)
            else:
                logger.critical('Ambiguous localid in "depends" : %s'%localid)
                self.generate_table(valid)
                raise ValueError('Ambiguous local id in "depends" %s:'%localid)
        todo.metadata["depends"] = result


# =============================================================================
#                           Parsing command line
# =============================================================================


def parse_args():
    import re
    # Huge args parser. I cannot use the (very good) argparse because
    # taskwarrior allows too much flexibility for argparse to handle.

    # First filtering layer : every option starting by two dashs is
    # intercepted and removed because it is aimed @taskwarrior-jp itself.
    remaining_args = []
    taskwarrior_jp_args = []
    i = 1
    while i<len(sys.argv):
        chunk = sys.argv[i]
        if chunk.startswith('--'):
            taskwarrior_jp_args.append(chunk)
            i+=1

            if chunk in ['--config', '--token']:
                if i >= len(sys.argv):
                    raise SyntaxError('Option "%s" requires a value.'%chunk)
                taskwarrior_jp_args.append(sys.argv[i])
                i+=1
        else:
            remaining_args.append(chunk)
            i+=1
     
    # Cannot really uses logger with the following 3 lines because the
    # --verbose and --quiet flags have not been parsed yet :-/       
    #print('ARGS  : %s'%str(sys.argv))
    #print('TWJP  :', taskwarrior_jp_args)
    #print('REMAIN:', remaining_args)

    # Now we treat args intended for the "taskwarrior" part of taskwarrior-jp

    # Reminder of taskwarrior official man page :
    # task <filter> <command> [ <mods> | <args> ]

    # Identifying the command
    commands = ['next', 'add', 'done', 'modify', 'edit', 'cat', 'annotate']
    idx = None
    for idx,word in enumerate(remaining_args):
        if word in commands:
            break
        if idx==len(remaining_args)-1:
            idx = None

    # Now splitting the args between filter, command, and mods/args
    if idx is None:
        filters = remaining_args
        command = 'next'
        mods_args = []
    else:
        command = remaining_args[idx]
        filters = remaining_args[:idx]
        mods_args = remaining_args[idx+1:]

    return filters, command, mods_args, taskwarrior_jp_args


if __name__=='__main__':
    filters, command, mods_args, taskwarrior_jp_args = parse_args()

    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--verbose', action="store_true")
    parser.add_argument('--quiet', action="store_true")
    parser.add_argument('--no-color', action="store_true")
    parser.add_argument('--color', action="store_true")
    parser.add_argument('--list-notebooks', action="store_true")
    parser.add_argument('--token', help="Joplin web clipper token.")
    parser.add_argument('--config', default='./tjp.ini', help="Taskwarrior-jp config file.")

    parser.add_argument('--all', action='store_true', dest="display_all",
                        help="Also display finished TODO.")
    parser.add_argument('--really-all', action="store_true", dest="display_really_all",
                        help="Display TODOs from every folder.")

    parser.epilog = """That's it for Taskwarrior-JP core options.
    For Taskwarrior usage, the syntax is :
    tjp.py FILTERS COMMAND OPTS. Command can be "next", "add", "modify", "edit", "done", "cat".
    """
    
    args = parser.parse_args(taskwarrior_jp_args)

    logging.basicConfig(level=logging.DEBUG)
    if args.verbose:
        logger.setLevel(level=logging.DEBUG)
    elif args.quiet:
        logger.setLevel(level=logging.WARNING)
    else:
        logger.setLevel(level=logging.INFO)

    logger.debug('Filters : %s'%filters)
    logger.debug('Command : %s'%command)
    logger.debug('ModsArgs : %s'%mods_args)
    logger.debug('tjp args : %s'%taskwarrior_jp_args)

    j = Joplin(args)
    if args.list_notebooks:
        j.list_notebooks()
    elif hasattr(j, 'do_'+command):
        getattr(j, 'do_'+command)(filters, mods_args)
