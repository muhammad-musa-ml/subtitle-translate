"""Build samples/demo.srt: 39 cues of original English narration with fixed, tight timing on some.

Usage: python -X utf8 make_demo.py OUT_SRT
"""
import sys

TEXT = [
    "[MUSIC]",
    "Welcome back. Today we're sharing one video\nwith a team of 12 people.",
    "First, upload the file. It's 2.4 GB,\nso give it a minute.",
    "<i>While that runs, set the title.</i>",
    "Keep it under 60 characters.",
    "Next, pick who can watch it.",
    "- Everyone on the team?\n- Only the 12 people on the list.",
    "Right, so we choose \"Private link\".",
    "Now add subtitles in 3 languages.",
    "Italian, Spanish and German are ready\nfrom the last project.",
    "The translation takes about 2 minutes\nfor a 10-minute video.",
    "Check every cue before you publish.",
    "A wrong number in a subtitle is worse\nthan a missing one.",
    "For example, \"1,200 downloads\" must\nstay \"1,200 downloads\".",
    "<i>Dates matter too: March 3, 2027.</i>",
    "If a line is too long, it won't fit\non a phone screen.",
    "Two lines, 42 characters each,\nis a good limit.",
    "Reading speed matters as well.",
    "People read about 17 characters\nper second.",
    "Anything faster feels like a blur.",
    "[applause]",
    "Now press Publish.",
    "The link works right away.",
    "Send it to the team on Monday at 9:30.",
    "You'll see views within 5 minutes.",
    "If someone can't watch, check the list.",
    "Each person needs their own account.",
    "- Can I share it outside the team?\n- Yes, but only for 7 days.",
    "That limit is the default,\nand you can change it.",
    "<i>We keep a copy for 30 days.</i>",
    "After that, we ask before deleting it.",
    "One last thing: the captions.",
    "Download them as a file if you like.",
    "The file is plain text with numbers\nand times.",
    "Edit it in any text editor.",
    "Just don't change the times by accident.",
    "That's all for today.",
    "Thanks for watching, and see you\nin the next one.",
    "[MUSIC]",
]
TIGHT = {14, 17, 19, 25, 29, 31}   # cue numbers timed at 17 characters per second


def plain(text):
    out, depth = [], 0
    for ch in text:
        if ch == "<":
            depth += 1
        elif ch == ">" and depth:
            depth -= 1
        elif not depth:
            out.append(ch)
    return "".join(out).replace("\n", " ")


def ts(ms):
    h, rest = divmod(ms, 3600000)
    m, rest = divmod(rest, 60000)
    s, milli = divmod(rest, 1000)
    return "%02d:%02d:%02d,%03d" % (h, m, s, milli)


def main():
    t = 1000
    blocks = []
    for n, text in enumerate(TEXT, start=1):
        cps = 17.0 if n in TIGHT else 13.5
        dur = int(round(max(1.6, len(plain(text)) / cps) * 100)) * 10
        blocks.append("%d\n%s --> %s\n%s\n" % (n, ts(t), ts(t + dur), text))
        t += dur + 200
    with open(sys.argv[1], "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(blocks))


main()
