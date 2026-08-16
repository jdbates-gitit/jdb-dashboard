"""
Interactive tool to flag (or unflag) entries in your Project Vote history,
and to view the full saved description of any past idea -- since the list
on screen only shows a title, this is how you read the rest.

Run this anytime from the root of your jdb-dashboard repo (same folder as
project_vote_log.json).
    - Type a number to toggle that entry's flag.
    - Type 'v' followed by a number (e.g. 'v3') to view its full description.
    - Type 'q' to quit.

Note: entries saved before this description-saving feature was added will
only show a title -- there was nothing to save yet at that point.

After flagging, don't forget to commit and push so the flag shows up on
the live dashboard:
    git add project_vote_log.json
    git commit -m "Flag project ideas"
    git push
"""

import json
import pathlib

LOG_FILE = pathlib.Path("project_vote_log.json")


def load_log():
    if not LOG_FILE.exists():
        print("FAILED: project_vote_log.json not found in current directory.")
        print("Run this from the root of your jdb-dashboard repo.")
        return None
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"FAILED: could not read project_vote_log.json ({e}).")
        return None


def save_log(entries):
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)


def print_list(entries):
    print("\n" + "=" * 60)
    print("PROJECT VOTE HISTORY  (most recent first)")
    print("=" * 60)
    display_order = list(enumerate(entries))[::-1]
    for idx, e in display_order:
        mark = "\u2605" if e.get("flagged") else " "
        tags = ", ".join(e.get("tags", []))
        print(f"[{idx:>2}] {mark}  {e['date']}  {e['title']}" + (f"  ({tags})" if tags else ""))


def print_details(e):
    print("\n" + "-" * 60)
    print(f"{e['date']}  \u2014  {e['title']}" + ("  \u2605 FLAGGED" if e.get("flagged") else ""))
    print("-" * 60)
    if e.get("idea"):
        print(f"Idea:      {e['idea']}")
    if e.get("why_now"):
        print(f"Why now:   {e['why_now']}")
    if e.get("smallest"):
        print(f"Smallest:  {e['smallest']}")
    if not any(e.get(k) for k in ("idea", "why_now", "smallest")):
        print("(No saved description for this entry -- it was voted before")
        print(" full descriptions started being saved, only the title survived.)")
    if e.get("tags"):
        print(f"Tags:      {', '.join(e['tags'])}")


def main():
    entries = load_log()
    if entries is None:
        return
    if not entries:
        print("No entries in project_vote_log.json yet -- nothing to flag.")
        return

    while True:
        print_list(entries)
        choice = input("\nNumber to toggle flag, 'v<number>' to view details, or 'q' to quit: ").strip().lower()

        if choice == "q":
            break

        if choice.startswith("v") and choice[1:].isdigit():
            i = int(choice[1:])
            if i not in range(len(entries)):
                print("Not a valid entry number -- try again.")
                continue
            print_details(entries[i])
            input("\nPress Enter to go back to the list...")
            continue

        if not choice.isdigit() or int(choice) not in range(len(entries)):
            print("Not a valid entry number -- try again.")
            continue

        i = int(choice)
        entries[i]["flagged"] = not entries[i].get("flagged", False)
        save_log(entries)
        state = "FLAGGED" if entries[i]["flagged"] else "unflagged"
        print(f"SUCCESS: '{entries[i]['title']}' is now {state}.")

    print("\nDone. Remember to git add / commit / push project_vote_log.json")
    print("if you want the flags to show up on the live dashboard.")


if __name__ == "__main__":
    main()
