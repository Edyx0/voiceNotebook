# Reddit posts

Revised on November 2, 2026. These posts are written for the developer's account. Publication status and links are recorded below after submission.

The drafts use concrete examples rather than a feature catalogue. They avoid invented stories, claims about time saved, and generic requests for engagement. Each discloses the developer's relationship to the app and the unofficial Google integration.

## r/notebooklm

**Title:** I made a Mac app to sort lecture recordings into NotebookLM notebooks

**Body:**

**Upload your lecture recordings to NotebookLM, sorted by class and week.**

voiceNotebook is a free Mac app I built for students who record lectures.

1. Choose Apple Voice Memos or a folder of recordings.
2. Add your class timetable, by hand or from a photo.
3. Check the matches and choose **Convert & upload**.

The app converts the audio and uploads it to the notebook for that class and week. Two lectures for the same course in week 5 go together. Uncertain matches need a manual check. Your original recordings stay untouched.

**Apple silicon, macOS 26+. Free and open source (MIT).**

```sh
brew install --cask edyx0/tap/voicenotebook
```

Source, screenshots and setup: https://github.com/Edyx0/voiceNotebook

It uses the unofficial notebooklm-py client. Uploads go to Google's NotebookLM service, and Google changes can break sign-in or uploads.

## r/macapps

**Title:** [OS] voiceNotebook: sort Voice Memos by class and upload them to NotebookLM

**Body:**

**voiceNotebook: upload lecture recordings to NotebookLM by class and week.**

I'm the developer. It's free and open source.

**Problem:** Lecture recordings need sorting before they can be useful in NotebookLM. Give voiceNotebook your timetable and a Voice Memos library or audio folder. It matches recordings to classes and uploads them to the right weekly notebook. Originals stay untouched.

**Comparison:** Compared with Voice Memos plus manual NotebookLM uploads, this adds timetable matching, audio conversion and weekly notebook routing. Voice Memos is still the recorder; this app handles the library and uploads.

**Pricing:** $0, MIT license, no paid tier. Source and screenshots: https://github.com/Edyx0/voiceNotebook

Apple silicon, macOS 26+. Signed and Apple-notarized. Install with:

```sh
brew install --cask edyx0/tap/voicenotebook
```

It uses the unofficial notebooklm-py client. Uploaded media goes to Google, and Google changes can break the connection.

## r/opensource: not submitted

The community's current Rule 3 says: "All AI-generated content is low-effort and ban worthy." An AI-assisted rewrite must not be submitted there as if it complied. Source: https://www.reddit.com/mod/opensource/rules/

## Student and study-hacks communities

Use only in communities whose current rules allow the developer to share a free tool. Published in r/studytips after checking Rule 3, which allows tasteful, relevant self-promotion.

**Title:** Free Mac app: upload lecture recordings to NotebookLM, sorted by class and week

**Body:**

**Upload lecture recordings to NotebookLM, already sorted by class and week.**

I built voiceNotebook for students who record lectures. It takes recordings from Apple Voice Memos or an audio folder, matches them against your class timetable, and uploads them to the right NotebookLM notebook.

For example, both of your chemistry lectures in week 5 go into the same notebook. You can then use NotebookLM with that week's lecture recordings together.

Choose your recordings, add your timetable, check the matches, and click **Convert & upload**. Your original audio stays untouched. You can enter the timetable yourself or import a photo and correct the result.

It's free and open source. I'm the developer. The packaged app needs an Apple silicon Mac with macOS 26 or newer:

```sh
brew install --cask edyx0/tap/voicenotebook
```

Source, screenshots and setup: https://github.com/Edyx0/voiceNotebook

It uses an unofficial NotebookLM client. Uploads go to Google, and Google changes can break the connection.

## Short version for an allowed promotion thread

**voiceNotebook** is a free Mac app I built to sort lecture recordings into NotebookLM notebooks by course and week. It reads Voice Memos or exported audio, matches it against your timetable, and lets you check uncertain matches. Original recordings stay untouched.

Voice Memos handles recording; NotebookLM handles studying. This handles the sorting and uploads between them. It's MIT-licensed, signed and Apple-notarized.

Apple silicon, macOS 26+: `brew install --cask edyx0/tap/voicenotebook`

It uses an unofficial NotebookLM client. Uploaded media goes to Google, and Google changes can break the connection.

Source and screenshots: https://github.com/Edyx0/voiceNotebook

## Publication log

- r/notebooklm: published with Discussion flair on November 2, 2026, as u/E-D-X. Verified on the community feed and the post page: https://www.reddit.com/r/notebooklm/comments/1xlxeom/i_made_a_mac_app_to_sort_lecture_recordings_into/
- r/notebooklm: body edited after feedback to put the upload benefit first, followed by three numbered setup steps. Reddit does not allow changing a published post's title; the original title remains.
- r/studytips: published and verified on the community feed and post page: https://www.reddit.com/r/studytips/comments/1xlxtfe/free_mac_app_upload_lecture_recordings_to/
- r/macapps: submitted once to the November 2026 App Pile megathread in the required Problem/Comparison/Pricing format. Reddit showed "Yorum gönderildi" (comment submitted), and the comment was verified under u/E-D-X: https://www.reddit.com/r/macapps/comments/1xks9uj/comment/19s15ogoeiblu/
- r/opensource: not submitted because Rule 3 prohibits AI-generated content.
- r/StudentHacks and r/studyhacks: restricted communities; the UI requires moderator approval before posting. No approval request or modmail was sent.
- r/study: its rules allow app promotion only in the weekly self-promotion megathread. The current search showed inquiries about the missing thread and old posts, not an eligible current weekly thread. No standalone promotion was submitted.

### Submitted MacApps comment

voiceNotebook: upload lecture recordings to NotebookLM by class and week.

I'm the developer. It's free and open source.

Problem: Sorting and uploading lecture recordings by hand. Give voiceNotebook your timetable and a Voice Memos library or audio folder. It matches recordings to classes and uploads them to the right weekly notebook. Originals stay untouched.

Comparison: Compared with Voice Memos plus manual NotebookLM uploads, this adds timetable matching, audio conversion and weekly notebook routing. Voice Memos is still the recorder; this app handles the library and uploads.

Pricing: $0, MIT license, no paid tier. Source and screenshots: https://github.com/Edyx0/voiceNotebook

Apple silicon, macOS 26+. Signed and Apple-notarized. Install: `brew install --cask edyx0/tap/voicenotebook`

It uses the unofficial notebooklm-py client. Uploaded media goes to Google, and Google changes can break the connection.
