#!/usr/bin/env python

"""
A web interface to training messages.

This is essentially the training part of pop3proxy.py.  Typical usage is to
run proxytrainer.py in the background, then feed it individual messages or
mailboxes using the proxytee.py script (or something similar).  Normally,
proxytee.py would be inserted somewhere in your mail processing pipeline.
"""

# This module is part of the spambayes project, which is Copyright 2002
# The Python Software Foundation and is covered by the Python Software
# Foundation license.

__author__ = "Skip Montanaro <skip@pobox.com> mostly theft from pop3proxy"
__credits__ = "Richie Hindle, Tim Peters, all the Spambayes folk."

try:
    True, False
except NameError:
    # Maintain compatibility with Python 2.2
    True, False = 1, 0

# mostly just brought over from pop3proxy.py
todo = """

Web training interface:

 o Functional tests.
 o Review already-trained messages, and purge them.
 o Keyboard navigation (David Ascher).  But aren't Tab and left/right
   arrow enough?
 o [Francois Granger] Show the raw spambrob number close to the buttons
   (this would mean using the extra X-Hammie header by default).
 o Add Today and Refresh buttons on the Review page.
 o "There are no untrained messages to display.  Return Home."


User interface improvements:

 o Once the pieces are on separate pages, make the paste box bigger.
 o Deployment: Windows executable?  atlaxwin and ctypes?  Or just
   webbrowser?
 o Save the stats (num classified, etc.) between sessions.
 o "Reload database" button.


New features:

 o "Send me an email every [...] to remind me to train on new
   messages."
 o "Send me a status email every [...] telling how many mails have been
   classified, etc."
 o Possibly integrate Tim Stone's SMTP code - make it use async, make
   the training code update (rather than replace!) the database.
 o Allow use of the UI without the POP3 proxy.
 o Remove any existing X-Spambayes-Classification header from incoming
   emails.
 o Whitelist.
 o Online manual.
 o Links to project homepage, mailing list, etc.
 o Edit settings through the web.
 o List of words with stats (it would have to be paged!) a la SpamSieve.


Code quality:

 o Move the UI into its own module.
 o Eventually, pull the common HTTP code from pop3proxy.py and Entrian
   Debugger into a library.
 o Cope with the email client timing out and closing the connection.
 o Lose the trailing dot from cached messages.


Info:

 o Slightly-wordy index page; intro paragraph for each page.
 o In both stats and training results, report nham and nspam - warn if
   they're very different (for some value of 'very').
 o "Links" section (on homepage?) to project homepage, mailing list,
   etc.


Gimmicks:

 o Classify a web page given a URL.
 o Graphs.  Of something.  Who cares what?
 o Zoe...!
"""

try:
    import cStringIO as StringIO
except ImportError:
    import StringIO

import os, sys, re, errno, getopt, time, bisect
import socket, asyncore, asynchat, cgi, urlparse, webbrowser
import mailbox, email.Header
from spambayes import storage, tokenizer, mboxutils
from spambayes.FileCorpus import FileCorpus, ExpiryFileCorpus
from spambayes.FileCorpus import FileMessageFactory, GzipFileMessageFactory
from email.Iterators import typed_subpart_iterator
from spambayes.Options import options

# HEADER_EXAMPLE is the longest possible header - the length of this one
# is added to the size of each message.
HEADER_FORMAT = '%s: %%s\r\n' % options.hammie_header_name
HEADER_EXAMPLE = '%s: xxxxxxxxxxxxxxxxxxxx\r\n' % options.hammie_header_name


class Listener(asyncore.dispatcher):
    """Listens for incoming socket connections and spins off
    dispatchers created by a factory callable.
    """

    def __init__(self, port, factory, factoryArgs=(),
                 socketMap=asyncore.socket_map):
        asyncore.dispatcher.__init__(self, map=socketMap)
        self.socketMap = socketMap
        self.factory = factory
        self.factoryArgs = factoryArgs
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setblocking(False)
        self.set_socket(s, socketMap)
        self.set_reuse_addr()
        if options.verbose:
            print "%s listening on port %d." % (self.__class__.__name__, port)
        self.bind(('', port))
        self.listen(5)

    def handle_accept(self):
        # If an incoming connection is instantly reset, eg. by following a
        # link in the web interface then instantly following another one or
        # hitting stop, handle_accept() will be triggered but accept() will
        # return None.
        result = self.accept()
        if result:
            clientSocket, clientAddress = result
            args = [clientSocket] + list(self.factoryArgs)
            if self.socketMap != asyncore.socket_map:
                self.factory(*args, **{'socketMap': self.socketMap})
            else:
                self.factory(*args)


class BrighterAsyncChat(asynchat.async_chat):
    """An asynchat.async_chat that doesn't give spurious warnings on
    receiving an incoming connection, and lets SystemExit cause an
    exit."""

    def handle_connect(self):
        """Suppress the asyncore "unhandled connect event" warning."""
        pass

    def handle_error(self):
        """Let SystemExit cause an exit."""
        type, v, t = sys.exc_info()
        if type == socket.error and v[0] == 9:  # Why?  Who knows...
            pass
        elif type == SystemExit:
            raise
        else:
            asynchat.async_chat.handle_error(self)


class UserInterfaceListener(Listener):
    """Listens for incoming web browser connections and spins off
    UserInterface objects to serve them."""

    def __init__(self, uiPort, socketMap=asyncore.socket_map):
        Listener.__init__(self, uiPort, UserInterface, (), socketMap=socketMap)
        print 'User interface url is http://localhost:%d' % (uiPort)


# Until the user interface has had a wider audience, I won't pollute the
# project with .gif files and the like.  Here's the viking helmet.
import base64
helmet = base64.decodestring(
"""R0lGODlhIgAYAPcAAEJCRlVTVGNaUl5eXmtaVm9lXGtrZ3NrY3dvZ4d0Znt3dImHh5R+a6GDcJyU
jrSdjaWlra2tra2tta+3ur2trcC9t7W9ysDDyMbGzsbS3r3W78bW78be78be973e/8bn/86pjNav
kc69re/Lrc7Ly9ba4vfWveTh5M7e79be79bn797n7+fr6+/v5+/v7/f3787e987n987n/9bn99bn
/9bv/97n997v++fv9+f3/+/v9+/3//f39/f/////9////wAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAACH5BAEAAB4ALAAAAAAiABgA
AAj+AD0IHEiwoMGDA2XI8PBhxg2EECN+YJHjwwccOz5E3FhQBgseMmK44KGRo0kaLHzQENljoUmO
NE74uGHDxQ8aL2GmzFHzZs6NNFr8yKHC5sOfEEUOVcHiR8aNFksi/LCCx1KZPXAilLHBAoYMMSB6
9DEUhsyhUgl+wOBAwQIHFsIapGpzaIcTVnvcSOsBhgUFBgYUMKAgAgqNH2J0aPjxR9YPJerqlYEi
w4YYExQM2FygwIHCKVBgiBChBIsXP5wu3HD2Bw8MC2JD0CygAIHOnhU4cLDA7QWrqfd6iBE5dQsH
BgJvHiDgNoID0A88V6AAAQSyjl16QIHXBwnNAwDIBAhAwDmDBAjQHyiAIPkC7DnUljhxwkGAAQHE
B+icIAGD8+clUMByCNjUUkEdlHCBAvflF0BtB/zHQAMSCjhYYBXsoFVBMWAQWH4AAFBbAg2UWOID
FK432AEO2ABRBwtsFuKDBTSAYgMghBDCAwwgwB4CClQAQ0R/4RciAQjYyMADIIwwAggN+PeWBTPw
VdAHHEjA4IMR8ojjCCaEEGUCFcygnUQxaEndbhBAwKQIFVAAgQMQHPZTBxrkqUEHfHLAAZ+AdgBR
QAAAOw==""")


class UserInterface(BrighterAsyncChat):
    """Serves the HTML user interface of the proxy."""

    # A couple of notes about the HTML here:
    #  o I've tried to keep content and presentation separate using
    #    one main stylesheet - no <font> tags, and no inline stylesheets
    #  o Form fields must specify their name and value attributes like
    #    this: "... name='n' value='v' ..." even if there is no default
    #    value.  This is so that setFieldValue can set the value.

    header = """<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.0 Transitional//EN">
             <html><head><title>Spambayes Proxy Trainer: %s</title>
             <style>
             body { font: 90%% arial, swiss, helvetica; margin: 0 }
             table { font: 90%% arial, swiss, helvetica }
             form { margin: 0 }
             .banner { background: #c0e0ff; padding=5; padding-left: 15;
                       border-top: 1px solid black;
                       border-bottom: 1px solid black }
             .header { font-size: 133%% }
             .content { margin: 15 }
             .messagetable td { padding-left: 1ex; padding-right: 1ex }
             .sectiontable { border: 1px solid #808080; width: 95%% }
             .sectionheading { background: fffae0; padding-left: 1ex;
                               border-bottom: 1px solid #808080;
                               font-weight: bold }
             .sectionbody { padding: 1em }
             .reviewheaders a { color: #000000; font-weight: bold }
             .stripe_on td { background: #dddddd }
             </style>
             </head>\n"""

    bodyStart = """<body>
                <div class='banner'>
                %s
                <span class='header'>Spambayes Proxy Trainer: %s</span></div>
                <div class='content'>\n"""

    footer = """</div>
             <form action='save' method='POST'>
             <table width='100%%' cellspacing='0'>
             <tr><td class='banner'>&nbsp;<a href='home'>Spambayes Proxy Trainer</a>,
             %s.
             <a href='http://www.spambayes.org/'>Spambayes.org</a></td>
             <td align='right' class='banner'>
             %s
             </td></tr></table></form>
             </body></html>\n"""

    saveButtons = """<input type='submit' name='how' value='Save'>&nbsp;&nbsp;
            <input type='submit' name='how' value='Save &amp; shutdown'>"""

    pageSection = """<table class='sectiontable' cellspacing='0'>
                  <tr><td class='sectionheading'>%s</td></tr>
                  <tr><td class='sectionbody'>%s</td></tr></table>
                  &nbsp;<br>\n"""

    summary = """Emails classified this session: <b>%(numSpams)d</b> spam,
                <b>%(numHams)d</b> ham, <b>%(numUnsure)d</b> unsure.<br>
              Total emails trained: Spam: <b>%(nspam)d</b>
                                     Ham: <b>%(nham)d</b><br>
              """

    wordQuery = """<form action='wordquery'>
                <input name='word' value='' type='text' size='30'>
                <input type='submit' value='Tell me about this word'>
                </form>"""

    review = """<p>The proxy trainer stores all the messages it sees.
             You can train the classifier based on those messages
             using the <a href='review'>Review messages</a> page."""

    reviewHeader = """<p>These are untrained emails, which you can use to
                   train the classifier.  Check the appropriate button for
                   each email, then click 'Train' below.  'Defer' leaves the
                   message here, to be trained on later.  Click one of the
                   Discard / Defer / Ham / Spam headers to check all of the
                   buttons in that section in one go.</p>
                   <form action='review' method='GET'>
                       <input type='hidden' name='prior' value='%d'>
                       <input type='hidden' name='next' value='%d'>
                       <input type='hidden' name='startAt' value='%d'>
                       <input type='hidden' name='howMany' value='%d'>
                       <table border='0' cellpadding='0' cellspacing='0'>
                       <tr><td><input type='submit' name='go'
                                      value='Previous day' %s>&nbsp;</td>
                           <td><input type='submit' name='go'
                                      value='Next day' %s>&nbsp;</td>
                           <td>&nbsp;&nbsp;&nbsp;&nbsp;</td>
                        </tr></table>
                   </form>
                   &nbsp;
                   <form action='review' method='POST'>
                   <table class='messagetable' cellpadding='0' cellspacing='0'>
                   """

    onReviewHeader = \
    """<script type='text/javascript'>
    function onHeader(type, switchTo)
    {
        if (document.forms && document.forms.length >= 2)
        {
            form = document.forms[1];
            for (i = 0; i < form.length; i++)
            {
                splitName = form[i].name.split(':');
                if (splitName.length == 3 && splitName[1] == type &&
                    form[i].value == switchTo.toLowerCase())
                {
                    form[i].checked = true;
                }
            }
        }
    }
    </script>
    """

    reviewSubheader = \
        """<tr><td><b>Messages classified as %s:</b></td>
          <td><b>From:</b></td>
          <td class='reviewheaders'><a href='javascript: onHeader("%s", "Discard");'>Discard</a></td>
          <td class='reviewheaders'><a href='javascript: onHeader("%s", "Defer");'>Defer</a></td>
          <td class='reviewheaders'><a href='javascript: onHeader("%s", "Ham");'>Ham</a></td>
          <td class='reviewheaders'><a href='javascript: onHeader("%s", "Spam");'>Spam</a></td>
          </tr>"""

    upload = """<form action='%s' method='POST'
                enctype='multipart/form-data'>
             Either upload a message %s file:
             <input type='file' name='file' value=''><br>
             Or paste one whole message (incuding headers) here:<br>
             <textarea name='text' rows='3' cols='60'></textarea><br>
             %s
             </form>"""

    uploadUnknown = """<form action='%s' method='POST'
                enctype='multipart/form-data'>
             Upload an unknown message %s file:
             <input type='file' name='file' value=''><br>
             %s
             </form>"""

    uploadSubmit = """<input type='submit' name='which' value='%s'>"""

    train = upload % ('train', "or mbox",
                      (uploadSubmit % "Train as Spam") + "&nbsp;" + \
                      (uploadSubmit % "Train as Ham"))

    classify = upload % ('classify', "", uploadSubmit % "Classify")

    def __init__(self, clientSocket, socketMap=asyncore.socket_map):
        # Grumble: asynchat.__init__ doesn't take a 'map' argument,
        # hence the two-stage construction.
        BrighterAsyncChat.__init__(self)
        BrighterAsyncChat.set_socket(self, clientSocket, socketMap)
        self.request = ''
        self.set_terminator('\r\n\r\n')
        self.helmet = helmet
        self.messageName = int(time.time())
        keys = state.unknownCorpus.keys()
        while self.messageName in keys:
            self.messageName += 100

    def collect_incoming_data(self, data):
        """Asynchat override."""
        self.request = self.request + data

    def found_terminator(self):
        """Asynchat override.
        Read and parse the HTTP request and call an on<Command> handler."""
        requestLine, headers = (self.request+'\r\n').split('\r\n', 1)
        try:
            method, url, version = requestLine.strip().split()
        except ValueError:
            self.pushError(400, "Malformed request: '%s'" % requestLine)
            self.close_when_done()
        else:
            method = method.upper()
            _, _, path, _, query, _ = urlparse.urlparse(url)
            params = cgi.parse_qs(query, keep_blank_values=True)
            if self.get_terminator() == '\r\n\r\n' and method == 'POST':
                # We need to read a body; set a numeric async_chat terminator.
                match = re.search(r'(?i)content-length:\s*(\d+)', headers)
                contentLength = int(match.group(1))
                if contentLength > 0:
                    self.set_terminator(contentLength)
                    self.request = self.request + '\r\n\r\n'
                    return

            if type(self.get_terminator()) is type(1):
                # We've just read the body of a POSTed request.
                self.set_terminator('\r\n\r\n')
                body = self.request.split('\r\n\r\n', 1)[1]
                match = re.search(r'(?i)content-type:\s*([^\r\n]+)', headers)
                contentTypeHeader = match.group(1)
                contentType, pdict = cgi.parse_header(contentTypeHeader)
                if contentType == 'multipart/form-data':
                    # multipart/form-data - probably a file upload.
                    bodyFile = StringIO.StringIO(body)
                    params.update(cgi.parse_multipart(bodyFile, pdict))
                else:
                    # A normal x-www-form-urlencoded.
                    params.update(cgi.parse_qs(body, keep_blank_values=True))

            # Convert the cgi params into a simple dictionary.
            plainParams = {}
            for name, value in params.iteritems():
                plainParams[name] = value[0]
            self.onRequest(path, plainParams)
            self.close_when_done()

    def onRequest(self, path, params):
        """Handles a decoded HTTP request."""
        if path == '/':
            path = '/Home'

        if path == '/helmet.gif':
            # XXX Why doesn't Expires work?  Must read RFC 2616 one day...
            inOneHour = time.gmtime(time.time() + 3600)
            expiryDate = time.strftime('%a, %d %b %Y %H:%M:%S GMT', inOneHour)
            extraHeaders = {'Expires': expiryDate}
            self.pushOKHeaders('image/gif', extraHeaders)
            self.push(self.helmet)
        else:
            try:
                name = path[1:].capitalize()
                handler = getattr(self, 'on' + name)
            except AttributeError:
                self.pushError(404, "Not found: '%s'" % path)
            else:
                # This is a request for a valid page; run the handler.
                self.pushOKHeaders('text/html')
                isKill = (params.get('how', '').lower().find('shutdown') >= 0)
                self.pushPreamble(name, showImage=(not isKill))
                handler(params)
                timeString = time.asctime(time.localtime())
                self.push(self.footer % (timeString, self.saveButtons))

    def pushOKHeaders(self, contentType, extraHeaders={}):
        timeNow = time.gmtime(time.time())
        httpNow = time.strftime('%a, %d %b %Y %H:%M:%S GMT', timeNow)
        self.push("HTTP/1.1 200 OK\r\n")
        self.push("Connection: close\r\n")
        self.push("Content-Type: %s\r\n" % contentType)
        self.push("Date: %s\r\n" % httpNow)
        for name, value in extraHeaders.items():
            self.push("%s: %s\r\n" % (name, value))
        self.push("\r\n")

    def pushError(self, code, message):
        self.push("HTTP/1.0 %d Error\r\n" % code)
        self.push("Content-Type: text/html\r\n")
        self.push("\r\n")
        self.push("<html><body><p>%d %s</p></body></html>" % (code, message))

    def pushPreamble(self, name, showImage=True):
        self.push(self.header % name)
        if name == 'Home':
            homeLink = name
        else:
            homeLink = "<a href='home'>Home</a> &gt; %s" % name
        if showImage:
            image = "<img src='helmet.gif' align='absmiddle'>&nbsp;"
        else:
            image = ""
        self.push(self.bodyStart % (image, homeLink))

    def setFieldValue(self, form, name, value):
        """Sets the default value of a field in a form.  See the comment
        at the top of this class for how to specify HTML that works with
        this function.  (This is exactly what Entrian PyMeld is for, but
        that ships under the Sleepycat License.)"""
        match = re.search(r"\s+name='%s'\s+value='([^']*)'" % name, form)
        if match:
            quotedValue = re.sub("'", "&#%d;" % ord("'"), value)
            return form[:match.start(1)] + quotedValue + form[match.end(1):]
        else:
            print >>sys.stderr, "Warning: setFieldValue('%s') failed" % name
            return form

    def trimAndQuote(self, field, limit, quote=False):
        """Trims a string, adding an ellipsis if necessary, and
        HTML-quotes it.  Also pumps it through email.Header.decode_header,
        which understands charset sections in email headers - I suspect
        this will only work for Latin character sets, but hey, it works for
        Francois Granger's name.  8-)"""
        sections = email.Header.decode_header(field)
        field = ' '.join([text for text, _ in sections])
        if len(field) > limit:
            field = field[:limit-3] + "..."
        return cgi.escape(field, quote)

    def onHome(self, params):
        """Serve up the homepage."""
        stateDict = state.__dict__
        stateDict.update(state.bayes.__dict__)
        # so the property() isn't as cool as we thought.  -ntp
        stateDict['nham'] = state.bayes.nham
        stateDict['nspam'] = state.bayes.nspam
        body = (self.pageSection % ('Status', self.summary % stateDict)+
                self.pageSection % ('Train on proxied messages', self.review)+
                self.pageSection % ('Train on a given message', self.train)+
                self.pageSection % ('Classify a message', self.classify)+
                self.pageSection % ('Word query', self.wordQuery))
        self.push(body)

    def doSave(self):
        """Saves the database."""
        self.push("<b>Saving... ")
        self.push(' ')
        state.bayes.store()
        self.push("Done</b>.\n")

    def onSave(self, params):
        """Command handler for "Save" and "Save & shutdown"."""
        self.doSave()
        if params['how'].lower().find('shutdown') >= 0:
            self.push("<b>Shutdown</b>. Goodbye.</div></body></html>")
            self.push(' ')
            self.socket.shutdown(2)
            self.close()
            raise SystemExit

    def onUpload(self, params):
        """Save a message for later training."""
        # Upload or paste?  Spam or ham?
        content = params.get('file') or params.get('text')

        # Convert platform-specific line endings into unix-style.
        content = content.replace('\r\n', '\n').replace('\r', '\n')

        # Single message or mbox?
        if content.startswith('From '):
            # Get a list of raw messages from the mbox content.
            class SimpleMessage:
                def __init__(self, fp):
                    self.guts = fp.read()
            contentFile = StringIO.StringIO(content)
            mbox = mailbox.PortableUnixMailbox(contentFile, SimpleMessage)
            messages = map(lambda m: m.guts, mbox)
        else:
            # Just the one message.
            messages = [content]

        for m in messages:
            message = state.unknownCorpus.makeMessage("%d"%self.messageName)
            message.setSubstance(m)
            state.unknownCorpus.addMessage(message)
            self.messageName += 1

        # Save the database and return a link Home and another training form.
        self.doSave()
        self.push("<p>OK.</p>")

    def onTrain(self, params):
        """Train on an uploaded or pasted message."""
        # Upload or paste?  Spam or ham?
        content = params.get('file') or params.get('text')
        isSpam = (params['which'] == 'Train as Spam')

        # Convert platform-specific line endings into unix-style.
        content = content.replace('\r\n', '\n').replace('\r', '\n')

        # Single message or mbox?
        if content.startswith('From '):
            # Get a list of raw messages from the mbox content.
            class SimpleMessage:
                def __init__(self, fp):
                    self.guts = fp.read()
            contentFile = StringIO.StringIO(content)
            mbox = mailbox.PortableUnixMailbox(contentFile, SimpleMessage)
            messages = map(lambda m: m.guts, mbox)
        else:
            # Just the one message.
            messages = [content]

        # Append the message(s) to a file, to make it easier to rebuild
        # the database later.   This is a temporary implementation -
        # it should keep a Corpus of trained messages.
        if isSpam:
            f = open("_pop3proxyspam.mbox", "a")
        else:
            f = open("_pop3proxyham.mbox", "a")

        # Train on the uploaded message(s).
        self.push("<b>Training...</b>\n")
        self.push(' ')
        for message in messages:
            tokens = tokenizer.tokenize(message)
            state.bayes.learn(tokens, isSpam)
            f.write("From pop3proxy@spambayes.org Sat Jan 31 00:00:00 2000\n")
            f.write(message)
            f.write("\n\n")

        # Save the database and return a link Home and another training form.
        f.close()
        self.doSave()
        self.push("<p>OK. Return <a href='home'>Home</a> or train again:</p>")
        self.push(self.pageSection % ('Train another', self.train))

    def keyToTimestamp(self, key):
        """Given a message key (as seen in a Corpus), returns the timestamp
        for that message.  This is the time that the message was received,
        not the Date header."""
        return long(key[:10])

    def getTimeRange(self, timestamp):
        """Given a unix timestamp, returns a 3-tuple: the start timestamp
        of the given day, the end timestamp of the given day, and the
        formatted date of the given day."""
        # This probably works on Summertime-shift days; time will tell.  8-)
        this = time.localtime(timestamp)
        start = (this[0], this[1], this[2], 0, 0, 0, this[6], this[7], this[8])
        end = time.localtime(time.mktime(start) + 36*60*60)
        end = (end[0], end[1], end[2], 0, 0, 0, end[6], end[7], end[8])
        date = time.strftime("%A, %B %d, %Y", start)
        return time.mktime(start), time.mktime(end), date

    def buildReviewKeys(self, timestamp):
        """Builds an ordered list of untrained message keys, ready for output
        in the Review list.  Returns a 5-tuple: the keys, the formatted date
        for the list (eg. "Friday, November 15, 2002"), the start of the prior
        page or zero if there isn't one, likewise the start of the given page,
        and likewise the start of the next page."""
        # Fetch all the message keys and sort them into timestamp order.
        allKeys = state.unknownCorpus.keys()
        allKeys.sort()

        # The default start timestamp is derived from the most recent message,
        # or the system time if there are no messages (not that it gets used).
        if not timestamp:
            if allKeys:
                timestamp = self.keyToTimestamp(allKeys[-1])
            else:
                timestamp = time.time()
        start, end, date = self.getTimeRange(timestamp)

        # Find the subset of the keys within this range.
        startKeyIndex = bisect.bisect(allKeys, "%d" % long(start))
        endKeyIndex = bisect.bisect(allKeys, "%d" % long(end))
        keys = allKeys[startKeyIndex:endKeyIndex]
        keys.reverse()

        # What timestamps to use for the prior and next days?  If there any
        # messages before/after this day's range, use the timestamps of those
        # messages - this will skip empty days.
        prior = end = 0
        if startKeyIndex != 0:
            prior = self.keyToTimestamp(allKeys[startKeyIndex-1])
        if endKeyIndex != len(allKeys):
            end = self.keyToTimestamp(allKeys[endKeyIndex])

        # Return the keys and their date.
        return keys, date, prior, start, end

    def appendMessages(self, lines, keyedMessages, label, startAt, howMany):
        """Appends the lines of a table of messages to 'lines'."""
        buttons = \
          """<td align='center'><input type='radio' name='classify:%s:%s' value='discard'></td>
             <td align='center'><input type='radio' name='classify:%s:%s' value='defer' %s></td>
             <td align='center'><input type='radio' name='classify:%s:%s' value='ham' %s></td>
             <td align='center'><input type='radio' name='classify:%s:%s' value='spam' %s></td>"""
        stripe = 0
        i = -1
        for key, message in keyedMessages:
            i += 1
            if i < startAt:
                continue
            if i >= startAt+howMany:
                break

            # Parse the message and get the relevant headers and the first
            # part of the body if we can.
            subject = self.trimAndQuote(message["Subject"] or "(none)", 50)
            from_ = self.trimAndQuote(message["From"] or "(none)", 40)
            try:
                part = typed_subpart_iterator(message, 'text', 'plain').next()
                text = part.get_payload()
            except StopIteration:
                try:
                    part = typed_subpart_iterator(message, 'text', 'html').next()
                    text = part.get_payload()
                    text, _ = tokenizer.crack_html_style(text)
                    text, _ = tokenizer.crack_html_comment(text)
                    text = tokenizer.html_re.sub(' ', text)
                    text = '(this message only has an HTML body)\n' + text
                except StopIteration:
                    text = '(this message has no text body)'
            text = text.replace('&nbsp;', ' ')      # Else they'll be quoted
            text = re.sub(r'(\s)\s+', r'\1', text)  # Eg. multiple blank lines
            text = self.trimAndQuote(text.strip(), 200, True)

            buttonLabel = label
            # classify unsure messages
            if buttonLabel == 'Unsure':
                tokens = tokenizer.tokenize(message)
                prob, clues = state.bayes.spamprob(tokens, evidence=True)
                if prob < options.ham_cutoff:
                    buttonLabel = 'Ham'
                elif prob >= options.spam_cutoff:
                    buttonLabel = 'Spam'

            # Output the table row for this message.
            defer = ham = spam = ""
            if buttonLabel == 'Spam':
                spam='checked'
            elif buttonLabel == 'Ham':
                ham='checked'
            elif buttonLabel == 'Unsure':
                defer='checked'
            subject = ('<span title="%s">'
                       '<a target=_top href="/view?key=%s&corpus=%s">'
                       '%s'
                       '</a>'
                       '</span>') % (text, key, label, subject)
            radioGroup = buttons % (buttonLabel, key,
                                    buttonLabel, key, defer,
                                    buttonLabel, key, ham,
                                    buttonLabel, key, spam)
            stripeClass = ['stripe_on', 'stripe_off'][stripe]
            lines.append("""<tr class='%s'><td>%s</td><td>%s</td>
                            %s</tr>""" % \
                            (stripeClass, subject, from_, radioGroup))
            stripe = stripe ^ 1

    def onReview(self, params):
        """Present a list of message for (re)training."""
        # Train/discard submitted messages.
        id = ''
        numTrained = 0
        numDeferred = 0
        startAt = 0
        howMany = 20
        for key, value in params.items():
            if key == 'startAt':
                startAt = int(value)
            elif key == 'howMany':
                howMany = int(value)
            elif key.startswith('classify:'):
                id = key.split(':')[2]
                if value == 'spam':
                    targetCorpus = state.spamCorpus
                elif value == 'ham':
                    targetCorpus = state.hamCorpus
                elif value == 'discard':
                    targetCorpus = None
                    try:
                        state.unknownCorpus.removeMessage(state.unknownCorpus[id])
                    except KeyError:
                        pass  # Must be a reload.
                else: # defer
                    targetCorpus = None
                    numDeferred += 1
                if targetCorpus:
                    try:
                        targetCorpus.takeMessage(id, state.unknownCorpus)
                        if numTrained == 0:
                            self.push("<p><b>Training... ")
                            self.push(" ")
                        numTrained += 1
                    except KeyError:
                        pass  # Must be a reload.

        # Report on any training, and save the database if there was any.
        if numTrained > 0:
            plural = ''
            if numTrained != 1:
                plural = 's'
            self.push("Trained on %d message%s. " % (numTrained, plural))
            self.doSave()
            self.push("<br>&nbsp;")

        # If any messages were deferred, show the same page again.
        if numDeferred > 0:
            start = self.keyToTimestamp(id)

        # Else after submitting a whole page, display the prior page or the
        # next one.  Derive the day of the submitted page from the ID of the
        # last processed message.
        elif id:
            start = self.keyToTimestamp(id)
            _, _, prior, _, next = self.buildReviewKeys(start)
            if prior:
                start = prior
            else:
                start = next

        # Else if they've hit Previous or Next, display that page.
        elif params.get('go') == 'Next day':
            start = self.keyToTimestamp(params['next'])
        elif params.get('go') == 'Previous day':
            start = self.keyToTimestamp(params['prior'])

        # Else show the most recent day's page, as decided by buildReviewKeys.
        else:
            start = 0

        # Build the lists of messages: spams, hams and unsure.
        keys, date, prior, this, next = self.buildReviewKeys(start)
        keyedMessages = {options.header_spam_string: [],
                         options.header_ham_string: [],
                         options.header_unsure_string: []}
        for key in keys:
            # Parse the message and get the judgement header.
            cachedMessage = state.unknownCorpus[key]
            message = mboxutils.get_message(cachedMessage.getSubstance())
            judgement = message[options.hammie_header_name]
            if judgement is None:
                judgement = options.header_unsure_string
            else:
                judgement = judgement.split(';')[0].strip()
            keyedMessages[judgement].append((key, message))

        # Present the list of messages in their groups in reverse order of
        # appearance.
        if keys:
            priorState = nextState = ""
            if not prior:
                priorState = 'disabled'
            if not next:
                nextState = 'disabled'
            lines = [self.onReviewHeader,
                     self.reviewHeader % (prior, next,
                                          startAt+howMany, howMany,
                                          priorState, nextState)]
            for header, label in ((options.header_spam_string, 'Spam'),
                                  (options.header_ham_string, 'Ham'),
                                  (options.header_unsure_string, 'Unsure')):
                if keyedMessages[header]:
                    lines.append("<tr><td>&nbsp;</td><td></td></tr>")
                    lines.append(self.reviewSubheader %
                                 (label, label, label, label, label))
                    self.appendMessages(lines, keyedMessages[header], label,
                                        startAt, howMany)

            lines.append("""<tr><td></td><td></td><td align='center' colspan='4'>&nbsp;<br>
                            <input type='submit' value='Train'></td></tr>""")
            lines.append("</table></form>")
            content = "\n".join(lines)
            title = "Untrained messages received on %s" % date
        else:
            content = "<p>There are no untrained messages to display.</p>"
            title = "No untrained messages"

        self.push(self.pageSection % (title, content))

    def onClassify(self, params):
        """Classify an uploaded or pasted message."""
        message = params.get('file') or params.get('text')
        message = message.replace('\r\n', '\n').replace('\r', '\n') # For Macs
        tokens = tokenizer.tokenize(message)
        prob, clues = state.bayes.spamprob(tokens, evidence=True)
        self.push("<p>Spam probability: <b>%.8f</b></p>" % prob)
        self.push("<table class='sectiontable' cellspacing='0'>")
        self.push("<tr><td class='sectionheading'>Clues:</td></tr>\n")
        self.push("<tr><td class='sectionbody'><table>")
        for w, p in clues:
            self.push("<tr><td>%s</td><td>%.8f</td></tr>\n" % (w, p))
        self.push("</table></td></tr></table>")
        self.push("<p>Return <a href='home'>Home</a> or classify another:</p>")
        self.push(self.pageSection % ('Classify another', self.classify))

    def onWordquery(self, params):
        word = params['word']
        word = word.lower()
        wi = state.bayes._wordinfoget(word)
        if wi:
            members = wi.__dict__
            members['spamprob'] = state.bayes.probability(wi)
            info = """Number of spam messages: <b>%(spamcount)d</b>.<br>
                   Number of ham messages: <b>%(hamcount)d</b>.<br>
                   Probability that a message containing this word is spam:
                   <b>%(spamprob)f</b>.<br>""" % members
        else:
            info = "%r does not appear in the database." % word

        query = self.setFieldValue(self.wordQuery, 'word', params['word'])
        body = (self.pageSection % ("Statistics for %r" % word, info) +
                self.pageSection % ('Word query', query))
        self.push(body)

    def onView(self, params):
        msgkey = corpus = None
        for key, value in params.items():
            if key == 'key':
                msgkey = value
            elif key == 'corpus':
                corpus = value
            if msgkey is not None and corpus is not None:
                message = state.unknownCorpus.get(msgkey)
                if message is None:
                    self.push("<p>Can't find message %s.\n" % msgkey)
                    self.push("Maybe it expired.</p>\n")
                else:
                    self.push("<pre>")
                    self.push(message.hdrtxt.replace("<", "&lt;"))
                    self.push("\n")
                    self.push(message.payload.replace("<", "&lt;"))
                    self.push("</pre>")
                msgkey = corpus = None

# This keeps the global state of the module - the command-line options,
# statistics like how many mails have been classified, the handle of the
# log file, the Classifier and FileCorpus objects, and so on.
class State:
    def __init__(self):
        """Initialises the State object that holds the state of the app.
        The default settings are read from Options.py and bayescustomize.ini
        and are then overridden by the command-line processing code in the
        __main__ code below."""
        # Open the log file.
        if options.verbose:
            self.logFile = open('_pop3proxy.log', 'wb', 0)

        # Load up the other settings from Option.py / bayescustomize.ini
        self.databaseFilename = options.pop3proxy_persistent_storage_file
        self.useDB = options.pop3proxy_persistent_use_database
        self.uiPort = options.html_ui_port
        self.launchUI = options.html_ui_launch_browser
        self.gzipCache = options.pop3proxy_cache_use_gzip
        self.cacheExpiryDays = options.pop3proxy_cache_expiry_days
        self.spamCache = options.pop3proxy_spam_cache
        self.hamCache = options.pop3proxy_ham_cache
        self.unknownCache = options.pop3proxy_unknown_cache
        self.runTestServer = False
        if self.gzipCache:
            factory = GzipFileMessageFactory()
        else:
            factory = FileMessageFactory()
        self.unknownCorpus = FileCorpus(factory, self.unknownCache)

        # Set up the statistics.
        self.totalSessions = 0
        self.activeSessions = 0
        self.numSpams = 0
        self.numHams = 0
        self.numUnsure = 0

        # Unique names for cached messages - see BayesProxy.onRetr
        self.lastBaseMessageName = ''
        self.uniquifier = 2

    def createWorkers(self):
        """Using the options that were initialised in __init__ and then
        possibly overridden by the driver code, create the Bayes object,
        the Corpuses, the Trainers and so on."""
        print "Loading database...",
        self.bayes = storage.DBDictClassifier(self.databaseFilename)
        print "Done."

        def ensureDir(dirname):
            try:
                os.mkdir(dirname)
            except OSError, e:
                if e.errno != errno.EEXIST:
                    raise

        # Create/open the Corpuses.
        map(ensureDir, [self.spamCache, self.hamCache, self.unknownCache])
        if self.gzipCache:
            factory = GzipFileMessageFactory()
        else:
            factory = FileMessageFactory()
        age = options.pop3proxy_cache_expiry_days*24*60*60
        self.spamCorpus = ExpiryFileCorpus(age, factory, self.spamCache)
        self.hamCorpus = ExpiryFileCorpus(age, factory, self.hamCache)
        self.unknownCorpus = FileCorpus(factory, self.unknownCache)

        # Expire old messages from the trained corpuses.
        self.spamCorpus.removeExpiredMessages()
        self.hamCorpus.removeExpiredMessages()

state = State()


def main(uiPort, launchUI):
    """Runs the proxy forever or until a 'KILL' command is received or
    someone hits Ctrl+Break."""
    UserInterfaceListener(uiPort)
    if launchUI:
        webbrowser.open_new("http://localhost:%d/" % uiPort)
    asyncore.loop()



# ===================================================================
# __main__ driver.
# ===================================================================

def run():
    # Read the arguments.
    try:
        opts, args = getopt.getopt(sys.argv[1:], 'htdbzp:l:u:')
    except getopt.error, msg:
        print >>sys.stderr, str(msg) + '\n\n' + __doc__
        sys.exit()

    for opt, arg in opts:
        if opt == '-h':
            print >>sys.stderr, __doc__
            sys.exit()
        elif opt == '-b':
            state.launchUI = True
        elif opt == '-d':
            state.useDB = True
        elif opt == '-p':
            state.databaseFilename = arg
        elif opt == '-l':
            state.proxyPorts = [int(arg)]
        elif opt == '-u':
            state.uiPort = int(arg)

    # Do whatever we've been asked to do...
    state.createWorkers()
    main(state.uiPort, state.launchUI)

if __name__ == '__main__':
    run()