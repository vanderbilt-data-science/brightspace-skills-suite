# Brightspace, Without the Busywork

**Hate wrestling with Brightspace? Let an AI assistant do it for you — just
tell it what you want, in plain English.**

No coding. No clicking through endless menus. You describe what you want for
your course, and the assistant does it — then shows you the result. It runs
in **Claude** — the Claude Desktop app (Claude Code) is the recommended and
verified home, with claude.ai as an option.

Created by **Jesse Spencer-Smith** (Vanderbilt Data Science Institute) and
**Claude Opus**.

---

## What it can do for you

Think of it as a capable teaching assistant who happens to be very fast and
never gets tired of Brightspace.

### 🏗️ Build your course
> *"Set up my fall course: syllabus, a module for each week, and the five
> lab assignments with their due dates."*

It creates the modules, posts your syllabus as a polished page, adds the
assignments, and can build quizzes and rubrics — matching a template if your
program has one, or starting clean. Reusing last term's course? Just say
*"copy my course from last year and move all the dates forward a year."*

### 🎬 Turn recordings into course videos
> *"Turn this Zoom recording into short course videos with captions and a
> quick check-for-understanding quiz, and publish them as Module 3."*

It chunks a class recording into concept-sized segments, adds branded intro
cards and captions, builds low-stakes quizzes, and publishes the whole
package into your course.

### 🔒 Coming after privacy review: grading & day-to-day class management

We've also built skills that grade submissions with AI-drafted feedback and
handle in-semester upkeep (announcements, deadline moves, "who hasn't
submitted?"). Because those touch **student data**, they are held out of
this main page while we finish a privacy and security review (FERPA /
Vanderbilt data-classification). They live on the
[`student-data-skills`](../../tree/student-data-skills) branch and will move
here once reviewed and approved. Please don't use them with real student
data until then.

---

## What it feels like to use

You talk to it like you'd text a sharp, reliable TA. You don't learn any
commands or menus. And it always **shows you a plan before it changes
anything** — so you're never surprised by what lands in your course.

A few real examples of things you can just say:

- *"Make my Brightspace course match this syllabus document."*
- *"Copy last year's course into my new shell — same structure, but I'll
  give you new content week by week."*
- *"Add a low-stakes quiz for Module 3 with five questions from the readings."*
- *"Create a grading rubric for the final project and attach it."*

---

## Your safety net

This was built by an instructor, with an instructor's worries in mind:

- **You approve before anything happens.** Every change is previewed first.
- **Student data stays out until it's proven safe.** The features that read
  student work or grades are parked on a separate branch pending a privacy
  review — they're not part of the default install.
- **It won't touch your live course by accident.** Working on the real,
  student-facing course takes a deliberate, extra "yes."
- **It double-checks its own work.** After making a change, it reads it back
  to confirm it actually took — Brightspace doesn't always cooperate, and
  this catches the silent failures.
- **It can't spam your students.** No mass emails, no surprise posts.

---

## Getting started

No downloading, no zipping — the skills install straight from this page.
One-time setup, about two minutes.

**Easiest: ask Claude to do it.** In **Claude Code** (in the Claude Desktop
app, or the terminal), just say:

> *"Install the skills from
> https://github.com/vanderbilt-data-science/brightspace-skills-suite"*

Claude installs them for you, and they're ready in your next chat.
(Prefer typing it yourself? The two commands are
`/plugin marketplace add vanderbilt-data-science/brightspace-skills-suite`,
then `/plugin` to pick and install the skills.)

**In Cowork** (the Claude Desktop app's file-working mode): open
**Customize → Plugins → Add marketplace**, paste
`vanderbilt-data-science/brightspace-skills-suite`, and click **Install**
on the skills you want. No files to handle.

**On claude.ai in the browser:** skills there are uploaded manually in
Settings — the steps are in the **[Technical Guide](TECHNICAL.md)**.

**Connecting to Brightspace is just logging in.** In your first chat, say
*"log me into Brightspace."* Claude opens Brightspace in its built-in
browser; you sign in the way you always do (university login + Duo — Claude
never touches your password), and you're connected. The connection uses
**your own account**, so Claude can only ever do what you could do
yourself — via a pass that expires every hour; Claude renews it as
needed and asks you to log in again only when your university session
has lapsed.

Then try:

> *"Copy my course from last year into my new fall shell — keep the
> structure, move all the dates forward a year."*

If a colleague already set this up for you, just open Claude and start
asking.

> **Tip:** the full experience — including help with the handful of
> Brightspace steps that need clicks in the browser — is in **Claude
> Code**, which is built into the Claude Desktop app.

---

## Good to know

- It uses **your own Brightspace login**, so it can only ever do what *you*
  could do yourself — nothing more.
- A few Brightspace features have no automated path (creating a rubric grid,
  building certain quiz question types). For those, the assistant walks you
  through the clicks and then confirms the result — you're never left
  guessing.
- This is a living project, built and tested on a real Brightspace course.
  Suggestions and problems are welcome — open an issue on this page.

---

*Created by Jesse Spencer-Smith and Claude Opus. Free to use and share under
the MIT License. Technical details: **[TECHNICAL.md](TECHNICAL.md)**.*
