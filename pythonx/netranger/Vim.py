import time

import vim

_hasnvim = int(vim.eval('has("nvim")'))

# original api
command = vim.command
current = vim.current
eval = vim.eval
vars = vim.vars
buffers = vim.buffers

if _hasnvim:

    def walk(fn, obj, *args, **kwargs):
        return obj
else:

    def walk(fn, obj, *args, **kwargs):
        """Recursively walk an object graph applying `fn`/`args` to objects."""
        objType = type(obj)
        if objType in [list, tuple, vim.List]:
            return list(walk(fn, o, *args) for o in obj)
        elif objType in [dict, vim.Dictionary]:
            return dict((walk(fn, k, *args), walk(fn, v, *args))
                        for k, v in obj.items())
        return fn(obj, *args, **kwargs)


if vim.eval('has("timers")') == "1" and not vim.vars.get("_NETRDebug", False):

    def Timer(delay, fn, pyfn, *args):
        if len(args):
            vim.command('call timer_start({}, function("{}", {}))'.format(
                delay, fn, list(args)))
        else:
            vim.command('call timer_start({}, "{}")'.format(delay, fn))
else:

    def Timer(delay, fn, pyfn, *args):
        pyfn(*args)


def log(*msg):
    with open('/tmp/netrlog', 'a') as f:
        f.write(' '.join([str(m) for m in msg]) + '\n')


def decode_if_bytes(obj, mode=True):
    """Decode obj if it is bytes."""
    if mode is True:
        mode = 'strict'
    if isinstance(obj, bytes):
        return obj.decode("utf-8", errors=mode)
    return obj


def VimChansend(job_id, msg):
    vim.command('chansend({},"{}\n")'.format(job_id, msg))


_NETRcbks = {}


def VimAsyncCallBack(job_id, event, data):
    cbk = _NETRcbks[job_id][event]
    if event == 'exit':
        cbk()
        del _NETRcbks[job_id]
    else:
        cbk(job_id, data)


def do_nothing_with_args(job_id, data):
    pass


def do_nothing():
    pass


if _hasnvim:

    def JobStart(cmd, display_progress=False):
        if not display_progress:
            vim.command('let g:NETRJobId = jobstart(\'{}\',\
                    {{"on_stdout":function("netranger#nvimAsyncCallBack"),\
                      "on_stderr":function("netranger#nvimAsyncCallBack"),\
                      "on_exit":function("netranger#nvimAsyncCallBack")}})'.
                        format(cmd))
        else:
            ori_win_nr = vim.eval('win_getid()')
            vim.command('10 new')
            cmd_win_nr = vim.eval('win_getid()')
            vim.command('let g:NETRJobId = termopen(\'{}\',\
                        {{"on_exit":{{j,d,e -> function("netranger#nvimAsyncDisplayCallBack")(j,d,e,{}, {})}} }})'
                        .format(cmd, ori_win_nr, cmd_win_nr, cmd_win_nr))
        return str(vim.vars['NETRJobId'])

else:

    def JobStart(cmd, display_progress=False):
        cur_time = str(time.time())
        if not display_progress:
            vim.command('call job_start(\'{0}\',\
                    {{"out_cb":{{job,data-> netranger#vimAsyncCallBack("{1}",data,"stdout")}},\
                      "err_cb":{{job,data-> netranger#vimAsyncCallBack("{1}",data,"stderr")}},\
                      "exit_cb":{{job,status-> netranger#vimAsyncCallBack("{1}",status,"exit")}} }})'
                        .format(cmd, cur_time))
        else:
            pass
        # wait for 'term' options in job_start to be implemented
        return cur_time


def AsyncRun(cmd,
             on_stdout=None,
             on_stderr=None,
             on_exit=None,
             display_progress=False):

    if on_stdout is None:
        on_stdout = do_nothing_with_args
    if on_stderr is None:
        on_stderr = do_nothing_with_args
    if on_exit is None:
        on_exit = do_nothing

    job_id = JobStart(cmd, display_progress=display_progress)
    _NETRcbks[job_id] = {
        'stdout': on_stdout,
        'stderr': on_stderr,
        'exit': on_exit
    }


def Var(name, default=None):
    if name not in vim.vars:
        return default
    return walk(decode_if_bytes, vim.vars[name])


def SetVar(name, value):
    vim.vars[name] = value


def ErrorMsg(exception):
    if hasattr(exception, 'output'):
        msg = exception.output.decode('utf-8')
    else:
        msg = str(exception)
    msg = msg.strip()
    if not msg:
        return
    vim.command(
        'unsilent echohl ErrorMsg | unsilent echo "{}" | echohl None '.format(
            msg.replace('"', '\\"')))


def debug(*msg):
    vim.command('unsilent echom "{}"'.format(' '.join([str(m) for m in msg])))


def WarningMsg(msg):
    vim.command(
        'unsilent echohl WarningMsg | unsilent echo "{}" | echohl None '.
        format(msg.replace('"', '\\"')))


def Echo(msg):
    vim.command('unsilent echo "{}"'.format(msg))


def UserInput(hint, default=''):
    vim.command('let g:NETRRegister=input("{}: ", "{}")'.format(hint, default))
    return decode_if_bytes(vim.vars['NETRRegister'])


_NETRlastWidth = None


def CurWinWidth(cache=False):
    global _NETRlastWidth
    if cache:
        return _NETRlastWidth
    ve = vim.options['virtualedit']
    vim.options['virtualedit'] = 'all'
    vim.command('norm! g$')
    _NETRlastWidth = int(vim.eval('virtcol(".")'))
    vim.command('norm! g0')
    vim.options['virtualedit'] = ve
    return _NETRlastWidth


def VimCurWinHeight():
    return int(vim.eval("winheight('.')"))


def tabdrop(path):
    for tab in vim.tabpages:
        for window in tab.windows:
            if window.buffer.name == path:
                vim.command("tabnext {}".format(tab.number))
                return
    vim.command("tabedit {}".format(path))


class pbar(object):
    def __init__(self, objects, total=None, chunkSize=100):
        self.objects = iter(objects)
        if total is None:
            self.total = len(objects)
        else:
            self.total = total
        self.cur = 0
        self.chunkSize = chunkSize
        self.wid = CurWinWidth()
        self.st_save = vim.current.window.options['statusline']

    def __iter__(self):
        return self

    def __next__(self):
        if self.cur == self.total:
            vim.current.window.options['statusline'] = self.st_save
            vim.command("redrawstatus!")
            raise StopIteration
        else:
            self.cur += 1
            if self.cur % self.chunkSize == 0:
                vim.current.window.options[
                    'statusline'] = "%#NETRhiProgressBar#{}%##".format(
                        ' ' * int(self.cur * self.wid / self.total))
                vim.command("redrawstatus!")
            return next(self.objects)
