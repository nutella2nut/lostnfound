# WORDING_AUDIT.md — Precise Wording Overhaul (§3)

All user-facing string changes made as part of §3 (Precise Wording Overhaul).

---

## §3.1 Claim Flow Wording (completed in Session 4)

File: templates/inventory/item_detail.html
  Before: Generic claim heading
  After:  "Claim this item" heading with attestation warning per §3.1.1

File: templates/inventory/item_detail.html
  Before: Simple claim form fields
  After:  "Full name (as it appears on your TISB record)" + "TISB email address" labels, dynamic attestation checkbox per §3.1.2

File: templates/inventory/item_detail.html
  Before: No confirmation modal
  After:  Pre-submit confirmation modal per §3.1.3

File: templates/inventory/item_detail.html
  Before: "Claim Item" button
  After:  "Submit claim" button per §3.1.2

File: inventory/views.py (ClaimItemView)
  Before: Generic claim success message
  After:  "Your claim has been recorded." + collection instructions per §3.1.4

File: inventory/views.py (ClaimItemView)
  Before: Generic claim email
  After:  Precise claim confirmation email per §3.1.5

## §3.2 Claimed-State Display (completed in Session 4)

File: templates/inventory/item_detail.html
  Before: "Claimed" badge
  After:  "Claim submitted — awaiting collection" / "{n} claims submitted" per §3.2

## §3.3 Browse / Landing / Empty States

File: templates/inventory/landing.html (line 64)
  Before: "Lost something at school? We've got it."
  After:  "Have you lost an item at school?"

File: templates/inventory/landing.html (line 78)
  Before: "Find Your Item"
  After:  "Search for your item"

File: templates/inventory/landing.html (line 79)
  Before: "Browse uploaded lost items with images and descriptions."
  After:  "Browse items that have been logged by staff, with images and descriptions."

File: templates/inventory/landing.html (line 93)
  Before: "Submit a claim request if the item looks like yours."
  After:  "Submit a formal claim if this is your personal property."

File: templates/inventory/landing.html (line 106)
  Before: "Collect Your Item"
  After:  "Collect in person"

File: templates/inventory/landing.html (line 107)
  Before: "Verify ownership and collect your item securely."
  After:  "Collect your item in person from the school reception during school hours with valid TISB identification."

File: templates/inventory/item_list.html (line 330)
  Before: "No items found matching your criteria." (always)
  After:  Conditional: with filter → "No items found matching your criteria." / without filter → "No items are currently listed in this view. New items appear here once they have been logged by staff and approved."

File: templates/inventory/primary_years_list.html (line 330)
  Before: "No items found matching your criteria." (always)
  After:  Conditional: with filter → "No items found matching your criteria." / without filter → "No items are currently listed in this view. New items appear here once they have been logged by staff and approved."

File: templates/inventory/admin_dashboard.html (line 275)
  Before: "No items found."
  After:  "No items are currently listed."

File: templates/inventory/student_lost_items_list.html (line 284) — already correct from Session 4
  Before: (unknown original)
  After:  "No student-submitted lost item reports are currently approved for display."

## §3.4 Submission-by-Email Instructions Page (completed in Session 3)

File: templates/inventory/how_to_report.html
  New file with verbatim wording per §3.4

## §3.5 Approval / Rejection Email Wording (completed in Session 3)

File: inventory/views.py (ApproveItemView)
  Before: Generic approval email
  After:  Precise approval email per §3.5.1

File: inventory/views.py (RejectItemView)
  Before: Generic rejection email
  After:  Precise rejection email per §3.5.2

## §3.6 Staff Upload Flow Wording

File: templates/inventory/item_upload.html (line 5)
  Before: "Upload Item - Trace Lost & Found"
  After:  "Log a Found Item - Trace Lost & Found"

File: templates/inventory/item_upload.html (line 192)
  Before: "Upload Lost & Found Item"
  After:  "Log a found item"

File: templates/inventory/item_upload.html (line 243)
  Before: "Images (Optional)"
  After:  "Photographs of the item (up to 3)"

File: templates/inventory/item_upload.html (line 272)
  Before: "Item Details"
  After:  "Item details — please be specific so the owner can identify it"

File: templates/inventory/item_upload.html (after description field)
  Before: No helper text
  After:  "Describe distinguishing features. For TISB notebooks, include colour, name (if visible), class/section, and subject. Do not record any personal information beyond what is on the item itself."

File: templates/inventory/item_upload.html (line 360)
  Before: "Save Item"
  After:  Super User: "Log item (will be published immediately)" / Admin: "Submit for Super User approval"

## §3.7 Footer / Global Disclaimer

Added to all 23 templates (17 staff sidebar + 5 public pages + 1 landing page):

  Text: "TRACE is operated by TISB. All claims and reports are logged. Misuse will be referred to the relevant Head of Year."

Staff sidebar templates (added inside sidebar, after nav):
  - templates/inventory/item_list.html
  - templates/inventory/primary_years_list.html
  - templates/inventory/admin_dashboard.html
  - templates/inventory/item_upload.html
  - templates/inventory/item_detail.html
  - templates/inventory/student_lost_item_detail.html
  - templates/inventory/student_lost_items_list.html
  - templates/inventory/approval_queue.html
  - templates/inventory/broadcast_confirm.html
  - templates/inventory/broadcast_history.html
  - templates/inventory/user_management/list.html
  - templates/inventory/user_management/create.html
  - templates/inventory/user_management/detail.html
  - templates/inventory/user_management/edit.html
  - templates/inventory/user_management/set_password.html
  - templates/inventory/user_management/delete.html
  - templates/inventory/user_management/role_change_history.html

Public pages (already had footer from Session 3/4, verified present):
  - templates/inventory/my_reports_signin.html
  - templates/inventory/my_reports_link_sent.html
  - templates/inventory/my_reports_link_invalid.html
  - templates/inventory/my_reports_dashboard.html
  - templates/inventory/how_to_report.html

Landing page (added as footer section):
  - templates/inventory/landing.html
