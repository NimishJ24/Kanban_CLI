import click
import urwid
from click_default_group import DefaultGroup
import yaml
import os
import sys
from textwrap import wrap
import collections
import datetime
import configparser
from rich import print
from rich.console import Console
from rich.table import Table
# import importlib

class Config(object):
    """The config in this example only holds aliases."""

    def __init__(self):
        self.path = os.getcwd() #get the current working directory
        self.aliases = {}

    def read_config(self, filename):
        parser = configparser.RawConfigParser()#used to read config file in raw format 
        parser.read([filename])
        try:
            self.aliases.update(parser.items('aliases'))
        except configparser.NoSectionError:
            pass

pass_config = click.make_pass_decorator(Config, ensure=True)
#make a decorator allowing click command to access files  
#ensure = True means object does not exist, it will be created and passed to the command.

class AliasedGroup(DefaultGroup):
    """This subclass of a group supports looking up aliases in a config
    file
    """

    def get_command(self, ctx, cmd_name):
        rv = click.Group.get_command(self, ctx, cmd_name)#click context obeject , command name
        if rv is not None:
            return rv

        # find the config object and ensure it's there.
        # This will create the config object is missing.
        cfg = ctx.ensure_object(Config)

        if cmd_name in cfg.aliases:
            actual_cmd = cfg.aliases[cmd_name]
            return click.Group.get_command(self, ctx, actual_cmd)

        matches = [x for x in self.list_commands(ctx)
                   if x.lower().startswith(cmd_name.lower())]
        if not matches:
            return None
        elif len(matches) == 1:
            return click.Group.get_command(self, ctx, matches[0])
        ctx.fail('Too many matches: %s' % ', '.join(sorted(matches)))

def read_config(ctx, param, value):
    """Callback that is used whenever --config is passed.  We use this to
    always load the correct config.  This means that the config is loaded
    even if the group itself never executes so our aliases stay always
    available.
    """
    cfg = ctx.ensure_object(Config)
    if value is None:
        value = os.path.join(os.path.dirname(__file__), 'aliases.ini')
    cfg.read_config(value)
    return value

@click.command(cls=AliasedGroup, default='show', default_if_no_args=True)
def kanbancli():
    """kanbancli: CLI personal kanban """

@kanbancli.command()
def configure():
    """Place default config file in KANBANCLI_HOME or HOME"""
    home = get_kanbancli_home()
    data_path = os.path.join(home, ".kanbancli.dat")
    config_path = os.path.join(home, ".kanbancli.yaml")
    if (os.path.exists(config_path) and not
            click.confirm('Config file exists. Do you want to overwrite?')):
        return
    with open(config_path, 'w') as outfile:
        conf = {'kanbancli_data': data_path}
        yaml.dump(conf, outfile, default_flow_style=False)
    click.echo("Creating %s" % config_path)

PRIORITY_MAP = {
    'high': 1,
    'medium': 2,
    'low': 3
}
@kanbancli.command()
@click.option('--name', '-n', required=True)
@click.option('--priority', type=click.Choice(['high', 'medium', 'low']), default='medium')
@click.argument('tasks',nargs=-1) # the number of command-line arguments that should be read
def add(tasks,priority,name):
    """Add a tasks in todo"""
    config = read_config_yaml()
    dd = read_data(config)
    taskname_length = 40

    for task in tasks:
        if len(task) > taskname_length:
            click.echo('Task must be at most %s chars, Brevity counts: %s'
                       % (taskname_length, task))
        else:
            todos,plans, inprogs, dones = split_items(config, dd)
            if ('limits' in config and 'todo' in config['limits'] and
                    int(config['limits']['todo']) <= len(todos)):
                click.echo('No new todos, limit reached already.')
            else:
                od = collections.OrderedDict(sorted(dd['data'].items()))
                new_id = 1        
                if bool(od):
                    new_id = next(reversed(od)) + 1
                entry = ['todo', task, timestamp(), timestamp(),PRIORITY_MAP[priority],name]
                dd['data'].update({new_id: entry})
                click.echo("Creating new task w/ id: %d -> %s"
                           % (new_id, task))

    write_data(config, dd)

@kanbancli.command()
@click.argument('ids', nargs=-1)
def delete(ids):
    """Delete task on the basis of task id"""
    config = read_config_yaml()
    dd = read_data(config)

    for id in ids:
        try:
            item = dd['data'].get(int(id))
            if item is None:
                click.echo('No existing task with that id: %d' % int(id))
            else:
                item[0] = 'deleted'
                item[2] = timestamp()
                dd['deleted'].update({int(id): item})
                dd['data'].pop(int(id))
                click.echo('Removed task %d.' % int(id))
        except ValueError:
            click.echo('Invalid task id')

    write_data(config, dd)

@kanbancli.command()
@click.argument('ids', nargs=-1)
def promote(ids):
    """Promote task on the basis of task id"""
    config = read_config_yaml()
    dd = read_data(config)
    todos,plans, inprogs, dones = split_items(config, dd)

    for id in ids:
        try:
            item = dd['data'].get(int(id))
            if item is None:
                click.echo('No existing task with that id: %s' % id)
            elif item[0] == 'todo':
                if ('limits' in config and 'wip' in config['limits'] and
                        int(config['limits']['wip']) <= len(inprogs)):
                    click.echo(
                        'Can not promote, in-progress limit of %s reached.'
                        % config['limits']['wip']
                    )
                else:
                    click.echo('Promoting task %s to plan.' % id)
                    dd['data'][int(id)] = [
                        'plan',
                        item[1], timestamp(),
                        item[3],item[4],item[5]
                    ]
            elif item[0] == 'plan':
                click.echo('Promoting task %s to in-progress.' % id)
                dd['data'][int(id)] = ['inprogress', item[1], timestamp(), item[3],item[4],item[5]]
            elif item[0] == 'inprogress':
                click.echo('Promoting task %s to done.' % id)
                dd['data'][int(id)] = ['done', item[1], timestamp(), item[3],item[4],item[5]]
            else:
                click.echo('Can not promote %s, already done.' % id)
        except ValueError:
            click.echo('Invalid task id')

    write_data(config, dd)

@kanbancli.command()
@click.argument('ids', nargs=-1)
def regress(ids):
    """Regress task on the basis of task id"""
    config = read_config_yaml()
    dd = read_data(config)

    todos,plans, inprogs, dones = split_items(config, dd)

    for id in ids:
        item = dd['data'].get(int(id))
        if item is None:
            click.echo('No existing task with id: %s' % id)
        elif item[0] == 'done':
            click.echo('Regressing task %s to in-progress.' % id)
            dd['data'][int(id)] = ['inprogress', item[1], timestamp(), item[3],item[4],item[5]]
        elif item[0] == 'inprogress':
            click.echo('Regressing task %s to plan.' % id)
            dd['data'][int(id)] = ['plan', item[1], timestamp(), item[3],item[4],item[5]]
        elif item[0] == 'plan':
            click.echo('Regressing task %s to todo.' % id)
            dd['data'][int(id)] = ['todo', item[1], timestamp(), item[3],item[4],item[5]]
        else:
            click.echo('Already in todo, can not regress %s' % id)

    write_data(config, dd)

@kanbancli.command()
@click.option('--name', '-n', help='Name of the Table', required=True)
def show(name):
    console = Console()
    """Show tasks in kanbancli"""
    config = read_config_yaml()
    dd = read_data(config)
   
    sorted_data = sorted(dd['data'].items(), key=lambda item: item[1][4])
    filtered_data = [item for item in sorted_data if item[1][5] == name]  # Assuming 6th element is at index 5

    # Prepare task lists based on filtered data
    filtered_todos = []
    filtered_plans = []
    filtered_inprogs = []
    filtered_dones = []
    for key, value in filtered_data:
        if value[0] == 'todo':
            filtered_todos.append("[%d] %s" % (key, value[1]))
        elif value[0] == 'plan':
            filtered_plans.append("[%d] %s" % (key, value[1]))
        elif value[0] == 'inprogress':
            filtered_inprogs.append("[%d] %s" % (key, value[1]))
        else:
            filtered_dones.insert(0, "[%d] %s" % (key, value[1]))

    if 'limits' in config and 'done' in config['limits']:
        filtered_dones = filtered_dones[0:int(config['limits']['done'])]
    else:
        filtered_dones = filtered_dones[0:10]

    todos = '\n'.join([str(x) for x in filtered_todos])
    plans = '\n'.join([str(x) for x in filtered_plans])
    inprogs = '\n'.join([str(x) for x in filtered_inprogs])
    dones = '\n'.join([str(x) for x in filtered_dones])

    table = Table(show_header=True, show_footer=True , title ="Your personal Kanban | {}".format(name) )
    table.add_column(
        "[bold yellow]todo[/bold yellow]",
        no_wrap=True,
        footer=name
    )
    table.add_column('[bold blue]plan[/bold blue]', no_wrap=True)
    table.add_column('[bold green]in-progress[/bold green]', no_wrap=True)
    table.add_column(
        '[bold magenta]done[/bold magenta]',
        no_wrap=True,
        footer="GDSC ROCKS"
    )

    table.add_row(todos,plans, inprogs, dones)
    console.print(table)

class KanbanCLIWidget(urwid.WidgetWrap):
    def __init__(self):
        super().__init__(self.main_view())
    

    def main_view(self):
        self.config = read_config_yaml()
        self.dd = read_data(self.config)

        tasks = self.get_task_list()
        self.task_widgets = self.create_task_widgets(tasks)

        # Create a ListBox to hold task widgets
        self.list_box = urwid.ListBox(urwid.SimpleFocusListWalker(self.task_widgets))

        return self.list_box

    def get_task_list(self):
        sorted_data = sorted(self.dd['data'].items(), key=lambda item: item[1][4])
        return [("[%d] %s" % (key, value[1]), key) for key, value in sorted_data]
    
    def create_task_widgets(self, tasks):
        return [urwid.Text(task[0]) for task in tasks]

    

    def mouse_event(self, size, event, button, col, row, focus):
        if event == 'mouse press':
            # Handle mouse press event
            # Determine the task being clicked on and start drag operation
            self.dragging_index = self.list_box.focus
            if self.dragging_index is not None:
                self.dragging = self.task_widgets[int(self.dragging_index)]
        elif event == 'mouse release':
            # Handle mouse release event
            # Determine drop location and perform drop operation
            if hasattr(self, 'dragging'):
                target_index = self.list_box.focus_position[1]
                self.drop_task(target_index)
                delattr(self, 'dragging')
                delattr(self, 'dragging_index')
        elif event == 'mouse drag':
            # Handle mouse drag event
            # Update display to reflect drag operation
            if hasattr(self, 'dragging'):
                self.list_box.body[self.dragging_index] = urwid.Text('Dragging: ' + self.dragging.text)
        return True
    
    def keypress(self, size, key):
        # If the keypress is a mouse event, handle it in the mouse_event method
        if urwid.is_mouse_event(key):
            return self.mouse_event(size, *key)
        else:
            return super().keypress(size, key)

    def drop_task(self, target_index):
        if target_index != self.dragging_index:
            # Reorder tasks based on drag and drop
            task_id_to_move = self.task_widgets[self.dragging_index].original_widget.task_id
            task_to_move = self.dd['data'].pop(task_id_to_move)
            self.dd['data'].insert(target_index, task_to_move)
            # Update task widgets
            self.task_widgets = self.create_task_widgets(self.get_task_list())
            # Update list box
            self.list_box.body = urwid.SimpleFocusListWalker(self.task_widgets)
            # Write updated data to the file
            write_data(self.config, self.dd)


#FUNCTIONS USED ABOVE :

def read_data(config):
    """Read the existing data from the config datasource"""
    try:
        with open(config["kanbancli_data"], 'r') as stream:
            try:
                return yaml.safe_load(stream)
            except yaml.YAMLError as exc:
                print("Ensure %s exists, as you specified it "
                      "as the kanbancli data file." % config['kanbancli_data'])
                print(exc)
    except IOError:
        click.echo("No data, initializing data file.")
        write_data(config, {"data": {}, "deleted": {}})
        with open(config["kanbancli_data"], 'r') as stream:
            return yaml.safe_load(stream)

def write_data(config, data):
    """Write the data to the config datasource"""
    with open(config["kanbancli_data"], 'w') as outfile:
        yaml.dump(data, outfile, default_flow_style=False)

def split_items(config, dd):
    todos = []
    plans=[]
    inprogs = []
    dones = []

    sorted_data = sorted(dd['data'].items(), key=lambda item: item[1][4])

    for key, value in sorted_data:
        if value[0] == 'todo':
            todos.append("[%d] %s" % (key, value[1]))
        elif value[0] == 'plan':
            plans.append("[%d] %s" % (key, value[1]))
        elif value[0] == 'inprogress':
            inprogs.append("[%d] %s" % (key, value[1]))
        else:
            dones.insert(0, "[%d] %s" % (key, value[1]))

    return todos,plans, inprogs, dones

def read_config_yaml():
    """Read the app config from ~/.kanbancli.yaml"""
    try:
        home = get_kanbancli_home()
        with open(home + "/.kanbancli.yaml", 'r') as ymfl:
            try:
                return yaml.safe_load(ymfl)
            except yaml.YAMLError:
                print("Ensure %s/.kanbancli.yaml is valid, expected YAML." % home)
                sys.exit()
    except IOError:
        print("Ensure %s/.kanbancli.yaml exists and is valid." % home)
        sys.exit()

def get_kanbancli_home():
    home = os.path.expanduser('~')
    return home

def timestamp():
    return '{:%Y-%b-%d %H:%M:%S}'.format(datetime.datetime.now())

#   MOUSE CONFIG
def main():
    # Create KanbanCLIWidget instance
    kanban_cli_widget = KanbanCLIWidget()

    # Create a loop widget to handle input and draw the UI
    loop = urwid.MainLoop(kanban_cli_widget)

    # Run the UI loop
    loop.run()

if __name__ == "__main__":
    main()



