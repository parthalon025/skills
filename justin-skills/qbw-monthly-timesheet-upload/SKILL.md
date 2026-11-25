---
name: "qbw-monthly-timesheet-upload"
description: "Use when Justin asks to upload or enter his monthly time sheet from the Project Time Tracker Excel file into QuickBooks Workforce."
---

# QuickBooks Workforce monthly timesheet upload

Input: the monthly tracker xlsx (example: Mcfarland_Justin_Monthly_Project_Time_Tracker.xlsx). Output: one time entry per worked day in QuickBooks Workforce, each with Assigned, Used, and Remaining hours.

## 1. Read the file
- Use openpyxl with data_only=True.
- Source of truth: column G (Hours Worked) with column A (Date). Use only rows where G has a value.
- Ignore columns H, I, J. They can disagree with G.
- Target: total hours per month = 80 (authorized billable hours; column F "Project Monthly Hours"). Sum column G. If the sum is not exactly 80.00, stop before entering anything. Tell the user the difference. Ask how to fix it (add or remove hours, and on which dates). Do not change hours without approval.
- Project name: column D. Employee: column C.

## 2. Defaults (confirmed by user)
- Customer: IS4S.
- Department: Executive (required field).
- Billable: checked.
- Notes: project name from column D.
- Assigned Hours: 80 on every entry.
- If the file or portal shows a different customer, project, or department, ask. Do not guess.

## 3. Formula for Hours used and Hours remaining
Sort the entries by date (oldest first). For entry i:
- Assigned = 80
- Used(i) = sum of Hours Worked for entries 1 through i (running total, includes the entry itself)
- Remaining(i) = 80 - Used(i)
- Round to 2 decimals. Compute in Python. Do not compute by hand.
- Check: the last entry must have Used = 80.00 and Remaining = 0.
- Example (October 2026): 10/5 8 h -> Used 8, Remaining 72. 10/6 8 h -> Used 16, Remaining 64. 10/8 3.01 h -> Used 19.01, Remaining 60.99. 10/30 3 h -> Used 80, Remaining 0.
- Spreadsheet formula equivalent (row r, column G = hours): Used = SUM($G$4:Gr). Remaining = 80 - Used.

## 4. Open the website
- Use Claude in Chrome. Run tabs_context_mcp first. Work in the tab the user has open. Do not open a new tab unless the user asks.
- If the tab is not on Time entries, navigate it to https://workforce.intuit.com/app/payroll-employee-portal-ui/portal/time
- Wait for the page to load (3 to 6 seconds). Take a screenshot. Confirm that "Time entries" is active and the company name shows (Quiet Professional Solutions LLC).
- If a sign-in page shows, stop. Ask the user to sign in. Never enter credentials or passwords.
- Default date range is the current week. Use the weekly entry screen to go back to the target month.
- Do not touch a running timer or entries outside the month.

## 5. Enter the hours (Add time > Weekly time entry)
- Do not use Single time entry for new days (one form per day).
- Move weeks with the < > arrows. Wait 3 seconds after each click. Clicks during loading are lost.
- Per week: Time category dropdown (row 1) > IS4S. Click the day cell, type the hours (decimal, for example 3.43). The grid shows h:mm (3.43 = 3:26). This is normal.
- Side panel for the first cell of a week: open Department (wait 1 s), choose Executive (wait 1 s), then set Billable and Notes.
- Billable on the first cell can fail to register or toggle off. Zoom on the panel to check the state before and after the click. Later cells in the same week inherit Department and Billable, so check them and only add Notes.
- Never press Escape. It closes the modal and discards unsaved entries.
- Do not type text into the panel without a screenshot first. A wrong click puts text in the Service field.
- Click Save after each week. Click Save and close after the last week.

## 6. Add Assigned, Used, and Remaining hours (edit each entry)
The weekly grid has no fields for these. Use the Edit link on each entry in Time entries (Date range > Last month, or Custom).
- Edit dialog fields (full-page coordinates): Assigned Hours (287, 388), Hours used (287, 455), Hours remaining (287, 522). Save (911, 661). Close X (1113, 28).
- Per entry: click Edit, wait 6 s, triple-click each field, type the value, then zoom on the dialog. Confirm the date in the dialog is the intended date BEFORE you click Save. The zoom region [0, 80, 1142, 560] shows date and fields.
- Save, wait 3 s, close the dialog, wait 6 s. Saving an existing entry shows "Time entry added." This is a normal message. It does not create a duplicate. Check that the entry count stays the same.
- The list is virtualized and the scroll resets to the top after each close. Use a fixed scroll recipe to get stable row positions: scroll down 15 ticks (bottom of list), then scroll up N ticks. Take a screenshot to read the Edit positions. Do not use positions from an earlier screenshot after a different scroll.
- Collapsed date rows (arrow >) hide their entry. Click the arrow to expand it first.
- Do ONE entry per verify cycle. Do not chain several unverified entries in one batch. A batch that runs without a date check can write the wrong values to the wrong entry.
- Do not put read_page in browser_batch. It is not a valid batch tool and the whole batch fails.

## 7. Verify
- Date range > Last month. Read the page text. Compare each date and hours value with the file. Check that Billable = Yes, Customer = IS4S, and the Notes are correct.
- Spot-check Assigned/Used/Remaining on the first entry, the last entry (80 / 80 / 0), and any entry that was edited twice.
- Confirm that the total of all entered hours for the month = 80.00 and the entry count equals the number of worked days.
- Entries show Unapproved. This is correct. Do not approve them.
- Report: number of entries, total hours, and any file inconsistency. Keep the report short.