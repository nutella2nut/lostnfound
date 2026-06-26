import logging
import os
import threading
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.mail import send_mail, EmailMessage, EmailMultiAlternatives
from django.core.paginator import Paginator
from django.core.signing import TimestampSigner, BadSignature, SignatureExpired
from django.db import transaction
from django.db.models import Q, Count
from django.http import JsonResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.views.generic import DetailView, ListView, TemplateView

from .forms import (
    ClaimItemForm, ItemForm, ItemImageFormSet,
    UserCreateForm, UserEditForm, UserSetPasswordForm,
)
from .models import (
    Item, UserProfile, StudentLostItem, StudentLostItemImage, Claim,
    ItemImage, BroadcastLog, MagicLinkRequest, UserRoleChangeLog,
)
from .services import analyze_item_images

User = get_user_model()
logger = logging.getLogger(__name__)


def send_system_email(subject: str, message: str, recipient_list: list[str]) -> None:
    """
    Helper for sending system emails.

    Sends asynchronously in a background thread so the web worker is not blocked
    by slow or failing SMTP connections (avoids Gunicorn WORKER TIMEOUT).
    Uses Django's EMAIL_* settings and fails silently if email is not configured.
    """
    if not recipient_list:
        return

    if not getattr(settings, "EMAIL_HOST", "") or not getattr(
        settings, "EMAIL_HOST_USER", ""
    ):
        # Email not configured – do nothing.
        return

    def _send():
        try:
            send_mail(
                subject=subject,
                message=message,
                from_email=getattr(
                    settings, "DEFAULT_FROM_EMAIL", settings.EMAIL_HOST_USER
                ),
                recipient_list=recipient_list,
                fail_silently=True,
            )
        except Exception:  # pragma: no cover - defensive logging
            import logging

            logger = logging.getLogger(__name__)
            logger.exception("Failed to send system email")

    thread = threading.Thread(target=_send, daemon=True)
    thread.start()


def is_super_user(user):
    """Check if user is a Super User for the Lost & Found system."""
    if not user.is_authenticated:
        return False
    return user.is_superuser


def is_admin(user):
    """Check if user is an Admin (staff but not Super User)."""
    if not user.is_authenticated:
        return False
    return user.is_staff and not is_super_user(user)


class SuperUserRequiredMixin(UserPassesTestMixin):
    """Only Super Users can access."""
    def test_func(self):
        return is_super_user(self.request.user)


class AdminOrSuperUserRequiredMixin(UserPassesTestMixin):
    """Admins and Super Users can access."""
    def test_func(self):
        user = self.request.user
        return user.is_authenticated and user.is_staff


class StaffRequiredMixin(UserPassesTestMixin):
    """Staff (Admin) only - Super Users should use AdminOrSuperUserRequiredMixin."""
    def test_func(self):
        user = self.request.user
        return user.is_authenticated and user.is_staff and not is_super_user(user)


class LandingPageView(TemplateView):
    template_name = "inventory/landing.html"


class ItemUploadView(LoginRequiredMixin, AdminOrSuperUserRequiredMixin, View):
    template_name = "inventory/item_upload.html"

    def get(self, request):
        item_form = ItemForm()
        formset = ItemImageFormSet()
        return render(
            request,
            self.template_name,
            {
                "item_form": item_form,
                "formset": formset,
            },
        )

    def post(self, request):
        item_form = ItemForm(request.POST)
        formset = ItemImageFormSet(request.POST, request.FILES)

        # Debug: Log form errors if any
        if not item_form.is_valid():
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Item form errors: {item_form.errors}")
        
        if not formset.is_valid():
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Formset errors: {formset.errors}, non_form_errors: {formset.non_form_errors}")

        if not (item_form.is_valid() and formset.is_valid()):
            return render(
                request,
                self.template_name,
                {
                    "item_form": item_form,
                    "formset": formset,
                },
            )

        item = item_form.save(commit=False)
        item.created_by = request.user

        # Set approval status based on user role
        if is_super_user(request.user):
            item.approval_status = Item.ApprovalStatus.APPROVED
            item.approved_by = request.user
            item.approved_at = timezone.now()
        else:
            item.approval_status = Item.ApprovalStatus.PENDING

        item.save()
        
        # Only save formset if there are images
        formset.instance = item
        if formset.has_changed():
            formset.save()

        if is_super_user(request.user):
            messages.success(
                request,
                f'Item "{item.title}" has been successfully uploaded and approved!',
            )
        else:
            messages.success(
                request,
                f'Item "{item.title}" has been successfully uploaded and is pending approval!',
            )
        return redirect(reverse("inventory:item_list"))


@require_http_methods(["POST"])
@csrf_exempt
def analyze_images_ajax(request):
    """AJAX endpoint to analyze images and return title/description suggestions."""
    if not (request.user.is_authenticated and request.user.is_staff):
        return JsonResponse({"error": "Unauthorized"}, status=403)
    
    uploaded_images = []
    for key in request.FILES:
        if key.startswith("image_"):
            uploaded_images.append(request.FILES[key])
    
    if not uploaded_images:
        return JsonResponse({"title": "", "description": ""})
    
    suggestions = analyze_item_images(uploaded_images)
    return JsonResponse(suggestions)


class ItemUploadConfirmView(LoginRequiredMixin, StaffRequiredMixin, View):
    template_name = "inventory/item_upload_confirm.html"

    def post(self, request):
        # Finalize save based on posted data
        item_form = ItemForm(request.POST)
        formset = ItemImageFormSet(request.POST, request.FILES)

        if not (item_form.is_valid() and formset.is_valid()):
            return render(
                request,
                self.template_name,
                {
                    "item_form": item_form,
                    "formset": formset,
                    "step": "confirm",
                },
            )

        item = item_form.save(commit=False)
        item.created_by = request.user
        item.save()
        formset.instance = item
        formset.save()

        messages.success(
            request,
            f'Item "{item.title}" has been successfully uploaded!',
        )
        return redirect(reverse("inventory:item_list"))

class ItemListView(ListView):
    model = Item
    template_name = "inventory/item_list.html"
    context_object_name = "items"
    paginate_by = 20

    def get_claim_duration_days(self, category):
        """Return the number of days a claimed item should remain visible based on category."""
        duration_map = {
            Item.Category.ELECTRONICS: 7,
            Item.Category.SPORTS_AND_CLOTHING: 3,
            Item.Category.BAGS_AND_CARRY: 1,
            Item.Category.BOTTLES_AND_CONTAINERS: 1,
            Item.Category.OTHER_MISC: 1,
            Item.Category.DOCUMENTS_AND_IDS: 1,  # Default for documents
            Item.Category.NOTEBOOKS_AND_BOOKS: 1,  # Default for notebooks
        }
        return duration_map.get(category, 1)

    def get_queryset(self):
        now = timezone.now()
        
        # Build Q objects for claimed items that are still within their category-specific duration
        claimed_q_objects = Q()
        for category, _ in Item.Category.choices:
            duration_days = self.get_claim_duration_days(category)
            cutoff_date = now - timedelta(days=duration_days)
            claimed_q_objects |= Q(
                status=Item.Status.CLAIMED,
                category=category,
                claimed_at__isnull=False,
                claimed_at__gte=cutoff_date
            )
        
        # Filter: Only approved items, only Senior Years items
        queryset = Item.objects.filter(
            Q(status=Item.Status.FOUND) | claimed_q_objects,
            approval_status=Item.ApprovalStatus.APPROVED,
            item_type=Item.ItemType.SENIOR,
        ).prefetch_related('images', 'claims')

        # Category filter
        category = self.request.GET.get("category")
        if category:
            queryset = queryset.filter(category=category)

        # Search query
        q = self.request.GET.get("q")
        if q:
            queryset = queryset.filter(
                Q(title__icontains=q) | Q(description__icontains=q)
            )

        location = self.request.GET.get("location")
        if location:
            queryset = queryset.filter(location_found__icontains=location)

        date_from = parse_date(self.request.GET.get("date_from") or "")
        if date_from:
            queryset = queryset.filter(date_found__gte=date_from)

        date_to = parse_date(self.request.GET.get("date_to") or "")
        if date_to:
            queryset = queryset.filter(date_found__lte=date_to)

        return queryset.order_by('-date_found', '-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['current_category'] = self.request.GET.get("category", "")
        context['search_query'] = self.request.GET.get("q", "")
        context['all_categories'] = Item.Category.choices
        return context


class ItemDetailView(DetailView):
    model = Item
    template_name = "inventory/item_detail.html"
    context_object_name = "item"
    
    def get_queryset(self):
        return Item.objects.prefetch_related('images', 'claims')


class ClaimItemView(View):
    """Handle item claiming — with attestation per §3.1."""
    http_method_names = ["post"]

    def post(self, request, pk):
        import logging
        logger = logging.getLogger(__name__)

        item = get_object_or_404(Item, pk=pk)
        form = ClaimItemForm(request.POST)

        if form.is_valid():
            name = form.cleaned_data["name"]
            email_addr = form.cleaned_data["email"]

            claim = Claim.objects.create(
                item=item,
                claimant_name=name,
                claimant_email=email_addr,
            )

            if item.status == Item.Status.FOUND:
                item.status = Item.Status.CLAIMED
                item.claimed_by_name = name
                item.claimed_at = timezone.now()
                item.save()

            # §3.1.5 Claim confirmation email
            base_url = getattr(settings, "MAGIC_LINK_BASE_URL", "") or ""
            claimed_at_ist = claim.claimed_at.astimezone(
                timezone.get_fixed_timezone(330)
            ).strftime("%-d %B %Y, %-I:%M %p IST")
            date_found_ist = item.date_found.strftime("%-d %B %Y")

            send_system_email(
                subject=f'Your claim has been recorded — "{item.title}"',
                message=(
                    f"Hi {name},\n\n"
                    "This email confirms that you have submitted a claim for the following "
                    "item through TRACE, the TISB Lost & Found system.\n\n"
                    f"Item:           {item.title}\n"
                    f"Category:       {item.get_category_display()}\n"
                    f"Found at:       {item.location_found}\n"
                    f"Found on:       {date_found_ist}\n"
                    f"Claim submitted: {claimed_at_ist}\n\n"
                    "To take possession of this item you must come in person to the school reception "
                    "during school hours. Please bring a valid form of TISB identification. The item "
                    "will only be released to you in person — it will not be released to any other "
                    "student, sibling, parent, or staff member acting on your behalf.\n\n"
                    f"You can view all your claims and lost-item reports at:\n"
                    f"{base_url}/my-reports/\n\n"
                    "If you did not submit this claim, reply to this email immediately so that "
                    "staff can investigate.\n\n"
                    "— TRACE, TISB Lost & Found"
                ),
                recipient_list=[email_addr],
            )

            # §3.1.4 Success banner
            messages.success(
                request,
                f"Your claim has been recorded. A confirmation has been sent to {email_addr}. "
                "To take possession of this item you must come in person to the school reception "
                "during school hours and present a valid form of TISB identification. "
                "Items will not be handed over to any person other than the named claimant.",
            )

            logger.info(
                "Item '%s' (ID: %s) claimed by %s (%s) at %s",
                item.title, item.pk, name, email_addr, claim.claimed_at,
            )
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, error)

        return redirect("inventory:item_detail", pk=pk)


class AdminDashboardView(LoginRequiredMixin, AdminOrSuperUserRequiredMixin, View):
    """Admin dashboard showing all items in a table with claim information."""
    template_name = "inventory/admin_dashboard.html"
    paginate_by = 50

    def get(self, request):
        from django.core.paginator import Paginator

        # Active items (FOUND / CLAIMED) — the main table
        active_items = Item.objects.filter(
            status__in=[Item.Status.FOUND, Item.Status.CLAIMED]
        ).prefetch_related('images', 'claims').order_by('-date_found', '-created_at')

        # Paginate active items
        paginator = Paginator(active_items, self.paginate_by)
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)

        # Collected items (picked up from reception)
        collected_qs = Item.objects.filter(
            status=Item.Status.COLLECTED
        ).prefetch_related('images', 'claims').order_by('-claimed_at', '-date_found')

        # Apply filters for collected items
        collected_category = request.GET.get('collected_category', '')
        if collected_category:
            collected_qs = collected_qs.filter(category=collected_category)

        collected_search = request.GET.get('collected_q', '').strip()
        if collected_search:
            collected_qs = collected_qs.filter(
                Q(title__icontains=collected_search) |
                Q(claimed_by_name__icontains=collected_search)
            )

        collected_date = request.GET.get('collected_date', '')
        if collected_date:
            from django.utils.dateparse import parse_date as _pd
            d = _pd(collected_date)
            if d:
                collected_qs = collected_qs.filter(claimed_at__date=d)

        collected_items = collected_qs

        # Get all claims for notification messages
        from .models import Claim

        # Get all recent claims (from the last 7 days to avoid too many old messages)
        from datetime import timedelta
        recent_cutoff = timezone.now() - timedelta(days=7)
        recent_claims = Claim.objects.filter(
            claimed_at__gte=recent_cutoff
        ).select_related('item').order_by('-claimed_at')

        # Create claim messages (stored in session to persist until dismissed)
        dismissed_message_ids = set(request.session.get('dismissed_message_ids', []))
        claim_messages = []

        # Add new claims that haven't been dismissed
        for claim in recent_claims:
            message_id = f"claim_{claim.pk}_{claim.claimed_at.timestamp()}"
            if message_id not in dismissed_message_ids:
                claim_messages.append({
                    'id': message_id,
                    'item_title': claim.item.title,
                    'claimant_name': claim.claimant_name,
                    'claimed_at': claim.claimed_at.isoformat(),
                    'item_id': claim.item.pk,
                })

        # Store dismissed message IDs in session (don't store all messages, just IDs)
        request.session['dismissed_message_ids'] = list(dismissed_message_ids)

        # Count claims per item for row coloring
        items_with_multiple_claims = set()
        for item in page_obj:
            if item.claim_count > 1:
                items_with_multiple_claims.add(item.pk)

        # Prepare claimants data for JavaScript (for the overlay)
        import json
        from django.core.serializers.json import DjangoJSONEncoder

        claimants_data = {}
        for item in page_obj:
            if item.claims.exists():
                claimants_data[item.pk] = [
                    {
                        'name': claim.claimant_name,
                        'claimed_at': claim.claimed_at.isoformat(),
                    }
                    for claim in item.claims.all()
                ]

        context = {
            'items': page_obj,
            'page_obj': page_obj,
            'is_paginated': page_obj.has_other_pages(),
            'claim_messages': claim_messages,
            'items_with_multiple_claims': items_with_multiple_claims,
            'claimants_data': json.dumps(claimants_data, cls=DjangoJSONEncoder),
            'collected_items': collected_items,
            'all_categories': Item.Category.choices,
            'collected_category': collected_category,
            'collected_search': collected_search,
            'collected_date': collected_date,
        }

        return render(request, self.template_name, context)

    def post(self, request):
        """Handle message dismissal and item deletion."""
        import json
        try:
            data = json.loads(request.body)
            if data.get('action') == 'dismiss_message':
                message_id = data.get('message_id')
                dismissed_ids = set(request.session.get('dismissed_message_ids', []))
                dismissed_ids.add(message_id)
                request.session['dismissed_message_ids'] = list(dismissed_ids)
                return JsonResponse({'success': True})
            elif data.get('action') == 'mark_collected':
                item_id = data.get('item_id')
                try:
                    item = Item.objects.get(pk=item_id)
                    item.status = Item.Status.COLLECTED
                    if not item.claimed_at:
                        item.claimed_at = timezone.now()
                    item.save()
                    return JsonResponse({'success': True, 'message': f'Item "{item.title}" marked as collected by student'})
                except Item.DoesNotExist:
                    return JsonResponse({'success': False, 'error': 'Item not found'}, status=404)
            elif data.get('action') == 'delete_item':
                item_id = data.get('item_id')
                try:
                    item = Item.objects.get(pk=item_id)
                    item_title = item.title
                    item.delete()
                    messages.success(request, f'Item "{item_title}" has been successfully deleted.')
                    return JsonResponse({'success': True, 'message': f'Item "{item_title}" deleted successfully'})
                except Item.DoesNotExist:
                    return JsonResponse({'success': False, 'error': 'Item not found'}, status=404)
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=400)
        
        return JsonResponse({'success': False}, status=400)


class PrimaryYearsListView(ListView):
    """Primary Years Lost and Found page - shows approved PY items."""
    model = Item
    template_name = "inventory/primary_years_list.html"
    context_object_name = "items"
    paginate_by = 20

    def get_claim_duration_days(self, category):
        """Return the number of days a claimed item should remain visible based on category."""
        duration_map = {
            Item.Category.ELECTRONICS: 7,
            Item.Category.SPORTS_AND_CLOTHING: 3,
            Item.Category.BAGS_AND_CARRY: 1,
            Item.Category.BOTTLES_AND_CONTAINERS: 1,
            Item.Category.OTHER_MISC: 1,
            Item.Category.DOCUMENTS_AND_IDS: 1,
            Item.Category.NOTEBOOKS_AND_BOOKS: 1,
        }
        return duration_map.get(category, 1)

    def get_queryset(self):
        now = timezone.now()
        
        # Build Q objects for claimed items that are still within their category-specific duration
        claimed_q_objects = Q()
        for category, _ in Item.Category.choices:
            duration_days = self.get_claim_duration_days(category)
            cutoff_date = now - timedelta(days=duration_days)
            claimed_q_objects |= Q(
                status=Item.Status.CLAIMED,
                category=category,
                claimed_at__isnull=False,
                claimed_at__gte=cutoff_date
            )
        
        # Filter: Only approved items, only Primary Years items
        queryset = Item.objects.filter(
            Q(status=Item.Status.FOUND) | claimed_q_objects,
            approval_status=Item.ApprovalStatus.APPROVED,
            item_type=Item.ItemType.PY,
        ).prefetch_related('images', 'claims')

        # Category filter
        category = self.request.GET.get("category")
        if category:
            queryset = queryset.filter(category=category)

        # Search query
        q = self.request.GET.get("q")
        if q:
            queryset = queryset.filter(
                Q(title__icontains=q) | Q(description__icontains=q)
            )

        location = self.request.GET.get("location")
        if location:
            queryset = queryset.filter(location_found__icontains=location)

        date_from = parse_date(self.request.GET.get("date_from") or "")
        if date_from:
            queryset = queryset.filter(date_found__gte=date_from)

        date_to = parse_date(self.request.GET.get("date_to") or "")
        if date_to:
            queryset = queryset.filter(date_found__lte=date_to)

        return queryset.order_by('-date_found', '-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['current_category'] = self.request.GET.get("category", "")
        context['search_query'] = self.request.GET.get("q", "")
        context['all_categories'] = Item.Category.choices
        return context


class StudentLostItemsListView(ListView):
    """Students' Lost Items page - shows approved student-submitted lost items."""
    model = StudentLostItem
    template_name = "inventory/student_lost_items_list.html"
    context_object_name = "items"
    paginate_by = 20

    def get_queryset(self):
        # Only show approved student lost items
        queryset = StudentLostItem.objects.filter(
            approval_status=StudentLostItem.ApprovalStatus.APPROVED
        ).prefetch_related('images')

        # Search query
        q = self.request.GET.get("q")
        if q:
            queryset = queryset.filter(
                Q(title__icontains=q) | Q(description__icontains=q)
            )

        return queryset.order_by('-submitted_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['search_query'] = self.request.GET.get("q", "")
        return context


class StudentLostItemDetailView(DetailView):
    """Detail view for student-submitted lost items."""
    model = StudentLostItem
    template_name = "inventory/student_lost_item_detail.html"
    context_object_name = "item"
    
    def get_queryset(self):
        # Only show approved items
        return StudentLostItem.objects.filter(
            approval_status=StudentLostItem.ApprovalStatus.APPROVED
        ).prefetch_related('images')


class ApprovalQueueView(LoginRequiredMixin, SuperUserRequiredMixin, ListView):
    """Approval queue for Super Users to approve/reject pending items.

    Supports tab switching via ?view= querystring:
      pending (default) — items awaiting approval
      to_broadcast — approved student items never broadcast
      broadcasts — all BroadcastLog entries
    """
    template_name = "inventory/approval_queue.html"
    context_object_name = "pending_items"
    paginate_by = 20

    def get_queryset(self):
        view = self.request.GET.get("view", "pending")

        if view == "to_broadcast":
            # Approved student lost items that have never been broadcast
            broadcast_student_ids = BroadcastLog.objects.filter(
                kind="STUDENT_LOST", student_lost_item__isnull=False
            ).values_list("student_lost_item_id", flat=True)
            items = StudentLostItem.objects.filter(
                approval_status=StudentLostItem.ApprovalStatus.APPROVED,
            ).exclude(pk__in=broadcast_student_ids).prefetch_related("images").order_by("-submitted_at")
            return [{"type": "student_item", "item": i} for i in items]

        if view == "broadcasts":
            return list(
                BroadcastLog.objects.select_related(
                    "student_lost_item", "found_item", "sent_by"
                ).order_by("-sent_at")
            )

        # Default: pending
        pending_items = []
        admin_items = Item.objects.filter(
            approval_status=Item.ApprovalStatus.PENDING
        ).prefetch_related('images', 'created_by').order_by('-created_at')
        for item in admin_items:
            pending_items.append({
                'type': 'admin_item',
                'item': item,
                'item_type_display': item.get_item_type_display(),
            })
        student_items = StudentLostItem.objects.filter(
            approval_status=StudentLostItem.ApprovalStatus.PENDING
        ).prefetch_related('images').order_by('-submitted_at')
        for item in student_items:
            pending_items.append({
                'type': 'student_item',
                'item': item,
            })
        pending_items.sort(key=lambda x: (
            x['item'].created_at if hasattr(x['item'], 'created_at') else x['item'].submitted_at
        ), reverse=True)
        return pending_items

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["current_view"] = self.request.GET.get("view", "pending")
        context['pending_admin_items_count'] = Item.objects.filter(
            approval_status=Item.ApprovalStatus.PENDING
        ).count()
        context['pending_student_items_count'] = StudentLostItem.objects.filter(
            approval_status=StudentLostItem.ApprovalStatus.PENDING
        ).count()
        # Count for "to broadcast" badge
        broadcast_student_ids = BroadcastLog.objects.filter(
            kind="STUDENT_LOST", student_lost_item__isnull=False
        ).values_list("student_lost_item_id", flat=True)
        context["to_broadcast_count"] = StudentLostItem.objects.filter(
            approval_status=StudentLostItem.ApprovalStatus.APPROVED,
        ).exclude(pk__in=broadcast_student_ids).count()
        return context


class ApproveItemView(LoginRequiredMixin, SuperUserRequiredMixin, View):
    """Approve a pending item (either Item or StudentLostItem)."""
    
    def post(self, request, item_type, item_id):
        if item_type == 'admin':
            item = get_object_or_404(Item, pk=item_id, approval_status=Item.ApprovalStatus.PENDING)
            item.approval_status = Item.ApprovalStatus.APPROVED
            item.approved_by = request.user
            item.approved_at = timezone.now()
            item.save()
            messages.success(request, f'Item "{item.title}" has been approved!')
            return redirect('inventory:approval_queue')
        elif item_type == 'student':
            item = get_object_or_404(
                StudentLostItem,
                pk=item_id,
                approval_status=StudentLostItem.ApprovalStatus.PENDING
            )
            item.approval_status = StudentLostItem.ApprovalStatus.APPROVED
            item.approved_by = request.user
            item.approved_at = timezone.now()
            item.save()
            # §3.5.1 Approval email
            if item.email_from:
                first_name = item.submitter_display_name.split()[0] if item.submitter_display_name else "there"
                base_url = getattr(settings, "MAGIC_LINK_BASE_URL", "") or ""
                send_system_email(
                    subject=f'Your lost item report has been approved — "{item.title}"',
                    message=(
                        f"Hi {first_name},\n\n"
                        "Your lost item report has been reviewed and approved by TRACE staff. "
                        "It is now visible on the Students' Lost Items page of TRACE.\n\n"
                        f"Item: {item.title}\n\n"
                        "If this item is found, you will be contacted at this email address. "
                        "To take possession of the item you must come in person to the school reception "
                        "during school hours and present a valid form of TISB identification.\n\n"
                        f"You can view your reports at: {base_url}/my-reports/\n\n"
                        "— TRACE, TISB Lost & Found"
                    ),
                    recipient_list=[item.email_from],
                )
            messages.success(request, f'Student lost item "{item.title}" has been approved!')
            return redirect('inventory:approval_queue')
        else:
            messages.error(request, 'Invalid item type.')
            return redirect('inventory:approval_queue')


class RejectItemView(LoginRequiredMixin, SuperUserRequiredMixin, View):
    """Reject a pending item (either Item or StudentLostItem)."""
    
    def post(self, request, item_type, item_id):
        rejection_reason = request.POST.get("rejection_reason", "").strip()[:500]

        if item_type == "admin":
            item = get_object_or_404(
                Item,
                pk=item_id,
                approval_status=Item.ApprovalStatus.PENDING,
            )
            item.approval_status = Item.ApprovalStatus.REJECTED
            item.approved_by = request.user
            item.approved_at = timezone.now()
            item.rejection_reason = rejection_reason
            item.save()
            messages.success(request, f'Item "{item.title}" has been rejected.')
            return redirect("inventory:approval_queue")
        elif item_type == "student":
            item = get_object_or_404(
                StudentLostItem,
                pk=item_id,
                approval_status=StudentLostItem.ApprovalStatus.PENDING,
            )
            item.approval_status = StudentLostItem.ApprovalStatus.REJECTED
            item.approved_by = request.user
            item.approved_at = timezone.now()
            item.rejection_reason = rejection_reason
            item.save()
            # §3.5.2 Rejection email
            if item.email_from:
                first_name = item.submitter_display_name.split()[0] if item.submitter_display_name else "there"
                submitted_at_ist = item.submitted_at.astimezone(
                    timezone.get_fixed_timezone(330)
                ).strftime("%-d %B %Y, %-I:%M %p IST")
                reason_line = ""
                if rejection_reason:
                    reason_line = f"Reason provided by staff: {rejection_reason}\n\n"
                send_system_email(
                    subject=f'Your lost item report was not approved — "{item.title}"',
                    message=(
                        f"Hi {first_name},\n\n"
                        f"Your lost item report submitted on {submitted_at_ist} was reviewed "
                        "by TRACE staff and was not approved for display.\n\n"
                        f"{reason_line}"
                        "If you believe this decision was made in error, or if you would like "
                        f"to resubmit with additional information, you may send a new email to "
                        f"{settings.LF_EMAIL_ADDRESS}. Please follow the submission format "
                        "described on the \"How to report a lost item\" page of TRACE.\n\n"
                        "— TRACE, TISB Lost & Found"
                    ),
                    recipient_list=[item.email_from],
                )
            messages.success(
                request, f'Student lost item "{item.title}" has been rejected.'
            )
            return redirect("inventory:approval_queue")
        else:
            messages.error(request, 'Invalid item type.')
            return redirect('inventory:approval_queue')


# ---------------------------------------------------------------------------
# Broadcast Views (§2)
# ---------------------------------------------------------------------------

def _get_base_url(request):
    """Build the base URL for absolute links in emails."""
    base = getattr(settings, "MAGIC_LINK_BASE_URL", "")
    if base:
        return base.rstrip("/")
    return f"{request.scheme}://{request.get_host()}"


class BroadcastItemView(LoginRequiredMixin, SuperUserRequiredMixin, View):
    """Broadcast an approved item to the school body (§2.4)."""

    def _get_item(self, kind, pk):
        if kind == "student-lost":
            return get_object_or_404(
                StudentLostItem, pk=pk,
                approval_status=StudentLostItem.ApprovalStatus.APPROVED,
            ), "STUDENT_LOST"
        elif kind == "found":
            return get_object_or_404(
                Item, pk=pk,
                approval_status=Item.ApprovalStatus.APPROVED,
            ), "FOUND_ITEM"
        return None, None

    def get(self, request, kind, pk):
        item, db_kind = self._get_item(kind, pk)
        if item is None:
            messages.error(request, "Invalid item type.")
            return redirect("inventory:landing")
        past_broadcasts = BroadcastLog.objects.filter(
            **{("student_lost_item" if db_kind == "STUDENT_LOST" else "found_item"): item}
        )
        recipients = getattr(settings, "LF_BROADCAST_RECIPIENTS_LIST", [])
        subject, body = self._compose_email(request, item, kind)
        return render(request, "inventory/broadcast_confirm.html", {
            "item": item,
            "kind": kind,
            "db_kind": db_kind,
            "subject": subject,
            "body": body,
            "recipients": recipients,
            "past_broadcasts": past_broadcasts,
            "broadcast_count": past_broadcasts.count(),
        })

    def post(self, request, kind, pk):
        item, db_kind = self._get_item(kind, pk)
        if item is None:
            messages.error(request, "Invalid item type.")
            return redirect("inventory:landing")

        # Rate limit: max 3 broadcasts per item per 24h (§2.9)
        cutoff = timezone.now() - timedelta(hours=24)
        fk_field = "student_lost_item" if db_kind == "STUDENT_LOST" else "found_item"
        recent_count = BroadcastLog.objects.filter(
            **{fk_field: item}, sent_at__gte=cutoff
        ).count()
        if recent_count >= 3:
            messages.error(
                request,
                "This item has already been broadcast 3 times in the last 24 hours. "
                "Please wait before sending again.",
            )
            return redirect(request.path)

        recipients = getattr(settings, "LF_BROADCAST_RECIPIENTS_LIST", [])
        if not recipients:
            messages.error(request, "No broadcast recipients configured.")
            return redirect(request.path)

        subject, body = self._compose_email(request, item, kind)
        email_address = getattr(settings, "LF_EMAIL_ADDRESS", settings.EMAIL_HOST_USER)
        display_name = getattr(settings, "LF_EMAIL_DISPLAY_NAME", "TRACE Lost & Found")
        from_email = f"{display_name} <{email_address}>"

        # Build email with attachments and HTML alternative
        html_body = self._render_html(request, item, kind)
        msg = EmailMultiAlternatives(
            subject=subject,
            body=body,
            from_email=from_email,
            to=[email_address],
            bcc=recipients,
            reply_to=[email_address],
        )
        msg.attach_alternative(html_body, "text/html")

        # Attach images (§2.6 — mandatory when images exist, 20MB total cap)
        images = self._get_images(item, db_kind)
        total_size = 0
        attached = 0
        for img in images:
            try:
                img.image.open("rb")
                data = img.image.read()
                img.image.close()
                if total_size + len(data) > 20 * 1024 * 1024:
                    break
                fname = os.path.basename(img.image.name)
                msg.attach(fname, data, "image/jpeg")
                total_size += len(data)
                attached += 1
            except Exception:
                logger.warning("Failed to attach image %s for broadcast", img.pk)

        if attached < len(images):
            body += (
                f"\n\n[Note: {len(images)} images were attached to the original report; "
                f"{attached} are included here. The remaining images are visible on TRACE "
                "at the link above.]"
            )
            msg.body = body

        succeeded = False
        error_message = ""
        try:
            msg.send(fail_silently=False)
            succeeded = True
        except Exception as e:
            error_message = str(e)[:500]
            logger.exception("Broadcast send failed for %s pk=%s", kind, pk)

        BroadcastLog.objects.create(
            kind=db_kind,
            **{fk_field: item},
            sent_by=request.user,
            recipients=", ".join(recipients),
            subject=subject,
            body_preview=body[:1000],
            succeeded=succeeded,
            error_message=error_message,
        )

        if succeeded:
            logger.info(
                "Broadcast sent: kind=%s item_id=%s sent_by=%s recipients_count=%d",
                db_kind, pk, request.user.username, len(recipients),
            )
            messages.success(request, "Broadcast email sent successfully.")
        else:
            messages.error(request, f"Broadcast failed: {error_message}")

        if db_kind == "FOUND_ITEM":
            return redirect("inventory:item_detail", pk=pk)
        return redirect("inventory:student_lost_items_list")

    def _get_images(self, item, db_kind):
        if db_kind == "STUDENT_LOST":
            return list(item.images.order_by("-created_at"))
        return list(item.images.order_by("-created_at"))

    def _compose_email(self, request, item, kind):
        base_url = _get_base_url(request)
        if kind == "student-lost":
            name = item.submitter_display_name or item.email_from
            ist = timezone.get_fixed_timezone(330)
            date_str = item.submitted_at.astimezone(ist).strftime("%-d %B %Y, %-I:%M %p IST")
            detail_url = base_url + reverse("inventory:student_lost_item_detail", args=[item.pk])
            subject = f'TISB Lost & Found — Lost item reported: "{item.title}"'
            body = (
                "A student has reported the following item as lost. If you have seen this item, "
                "or if you have it in your possession, please bring it to the school reception in person.\n\n"
                f"Item: {item.title}\n\n"
                f"Description:\n{item.description}\n\n"
                f"Reported by: {name}\n"
                f"Date reported: {date_str}\n\n"
                f"Photographs of the item are attached to this email and can also be viewed "
                f"in full resolution on TRACE:\n{detail_url}\n\n"
                "If this item is yours and has been found, you must collect it in person from "
                "the school reception. The Lost & Found system does not release items to anyone "
                "other than the rightful owner, in person.\n\n"
                "This email was sent by the TISB Lost & Found staff via TRACE.\n"
                "— TRACE, TISB Lost & Found"
            )
        else:
            detail_url = base_url + reverse("inventory:item_detail", args=[item.pk])
            ist = timezone.get_fixed_timezone(330)
            date_str = item.date_found.strftime("%-d %B %Y")
            subject = f'TISB Lost & Found — Item found: "{item.title}"'
            body = (
                "An item has been found and logged by TRACE staff. If you recognise this item "
                "as your personal property, please come to the school reception in person to claim it.\n\n"
                f"Item: {item.title}\n"
                f"Category: {item.get_category_display()}\n"
                f"Found at: {item.location_found}\n"
                f"Found on: {date_str}\n\n"
                f"Description:\n{item.description}\n\n"
                f"Photographs of the item are attached to this email and can also be viewed "
                f"in full resolution on TRACE:\n{detail_url}\n\n"
                "To take possession of this item you must come in person to the school reception "
                "during school hours and present a valid form of TISB identification. Items will "
                "not be handed over to any person other than the rightful owner, in person.\n\n"
                "This email was sent by the TISB Lost & Found staff via TRACE.\n"
                "— TRACE, TISB Lost & Found"
            )
        return subject, body

    def _render_html(self, request, item, kind):
        """Render the HTML email template for the broadcast."""
        base_url = _get_base_url(request)
        if kind == "student-lost":
            name = item.submitter_display_name or item.email_from
            ist = timezone.get_fixed_timezone(330)
            date_str = item.submitted_at.astimezone(ist).strftime("%-d %B %Y, %-I:%M %p IST")
            detail_url = base_url + reverse("inventory:student_lost_item_detail", args=[item.pk])
            return render_to_string("inventory/email/broadcast_student_lost.html", {
                "title": item.title,
                "description": item.description,
                "reported_by": name,
                "date_reported": date_str,
                "detail_url": detail_url,
            })
        else:
            ist = timezone.get_fixed_timezone(330)
            date_str = item.date_found.strftime("%-d %B %Y")
            detail_url = base_url + reverse("inventory:item_detail", args=[item.pk])
            return render_to_string("inventory/email/broadcast_found_item.html", {
                "title": item.title,
                "description": item.description,
                "category": item.get_category_display(),
                "location_found": item.location_found,
                "date_found": date_str,
                "detail_url": detail_url,
            })


class BroadcastHistoryView(LoginRequiredMixin, SuperUserRequiredMixin, ListView):
    """Audit log of all broadcasts (§2.8)."""
    model = BroadcastLog
    template_name = "inventory/broadcast_history.html"
    context_object_name = "broadcasts"
    paginate_by = 50

    def get_queryset(self):
        qs = BroadcastLog.objects.select_related("sent_by", "student_lost_item", "found_item")
        kind = self.request.GET.get("kind")
        if kind in ("STUDENT_LOST", "FOUND_ITEM"):
            qs = qs.filter(kind=kind)
        return qs


# ---------------------------------------------------------------------------
# How-to-Report Page (§3.4)
# ---------------------------------------------------------------------------

class HowToReportLostView(TemplateView):
    """Public page explaining how to report a lost item by email (§3.4)."""
    template_name = "inventory/how_to_report.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["email_address"] = getattr(settings, "LF_EMAIL_ADDRESS", "")
        return ctx


# ---------------------------------------------------------------------------
# Magic Link "My Reports" Views (§4)
# ---------------------------------------------------------------------------

def _magic_link_signer():
    secret = getattr(settings, "MAGIC_LINK_SECRET", "") or settings.SECRET_KEY
    return TimestampSigner(key=secret, salt="magic-link")


class MyReportsView(View):
    """Shows sign-in form or dashboard depending on session (§4.4)."""

    def get(self, request):
        email = request.session.get("magic_link_email")
        if email:
            return self._render_dashboard(request, email)
        return render(request, "inventory/my_reports_signin.html")

    def _render_dashboard(self, request, email):
        reports = StudentLostItem.objects.filter(
            email_from__iexact=email
        ).order_by("-submitted_at").prefetch_related("images", "broadcasts")
        claims = Claim.objects.filter(
            claimant_email__iexact=email
        ).select_related("item").order_by("-claimed_at")
        return render(request, "inventory/my_reports_dashboard.html", {
            "email": email,
            "reports": reports,
            "claims": claims,
        })


class RequestMagicLinkView(View):
    """Accept email, send magic link (§4.5.2)."""

    def post(self, request):
        email = (request.POST.get("email") or "").strip().lower()
        if not email.endswith("@tisb.ac.in"):
            return render(request, "inventory/my_reports_signin.html", {
                "error": "Only @tisb.ac.in email addresses are accepted.",
                "email_value": email,
            })

        # Rate limit: 3 per hour per email (§4.5.2)
        cutoff = timezone.now() - timedelta(hours=1)
        recent = MagicLinkRequest.objects.filter(
            email=email, requested_at__gte=cutoff
        ).count()
        if recent >= 3:
            return render(request, "inventory/my_reports_signin.html", {
                "error": "You have requested too many sign-in links recently. Please wait an hour and try again.",
                "email_value": email,
            })

        mlr = MagicLinkRequest.objects.create(
            email=email,
            ip_address=request.META.get("REMOTE_ADDR"),
            user_agent=request.META.get("HTTP_USER_AGENT", "")[:500],
        )

        signer = _magic_link_signer()
        token = signer.sign_object({"email": email, "req_id": mlr.pk})

        base_url = _get_base_url(request)
        sign_in_url = base_url + reverse("inventory:magic_link_signin", args=[token])

        send_system_email(
            subject="Your TRACE sign-in link",
            message=(
                "Hi,\n\n"
                "You requested a sign-in link to view your TRACE Lost & Found reports.\n\n"
                "Click the link below to sign in. The link is valid for 24 hours and can be used once.\n\n"
                f"{sign_in_url}\n\n"
                "If you did not request this link, ignore this email. No action is needed.\n\n"
                "— TRACE, TISB Lost & Found"
            ),
            recipient_list=[email],
        )
        logger.info("Magic link requested for email, req_id=%d", mlr.pk)
        return render(request, "inventory/my_reports_link_sent.html", {"email": email})


class MagicLinkSignInView(View):
    """Verify token, set session (§4.5.3)."""

    def get(self, request, token):
        signer = _magic_link_signer()
        try:
            payload = signer.unsign_object(token, max_age=86400)
        except (BadSignature, SignatureExpired):
            return render(request, "inventory/my_reports_link_invalid.html", {
                "message": "This sign-in link is invalid or has expired. Please request a new one.",
            })

        email = payload.get("email", "")
        req_id = payload.get("req_id")

        try:
            mlr = MagicLinkRequest.objects.get(pk=req_id)
        except MagicLinkRequest.DoesNotExist:
            return render(request, "inventory/my_reports_link_invalid.html", {
                "message": "This sign-in link is invalid or has expired. Please request a new one.",
            })

        if mlr.consumed_at:
            return render(request, "inventory/my_reports_link_invalid.html", {
                "message": "This sign-in link has already been used. Please request a new one if you need to sign in again.",
            })

        mlr.consumed_at = timezone.now()
        mlr.save(update_fields=["consumed_at"])

        request.session["magic_link_email"] = email
        request.session["magic_link_signed_in_at"] = timezone.now().isoformat()
        request.session.set_expiry(86400)

        return redirect("inventory:my_reports")


class MyReportsSignOutView(View):
    """Clear magic-link session (§4.5.5)."""

    def post(self, request):
        request.session.pop("magic_link_email", None)
        request.session.pop("magic_link_signed_in_at", None)
        return redirect("inventory:my_reports")


# ---------------------------------------------------------------------------
# Staff User Management Views (§6)
# ---------------------------------------------------------------------------

def _get_user_role(user):
    """Return role string for a user."""
    if not user.is_active:
        return "deactivated"
    if user.is_superuser:
        return "superuser"
    if user.is_staff:
        return "admin"
    return "no_staff"


def _log_role_change(target, performer, action, details=""):
    UserRoleChangeLog.objects.create(
        target_user=target,
        target_username_snapshot=target.username if target else "",
        performed_by=performer,
        performed_by_username_snapshot=performer.username if performer else "",
        action=action,
        details=details,
    )


def _send_role_notification(target_user, performer, action, password=None):
    """Send role-change email notification (§6.10)."""
    name = target_user.first_name or target_user.username
    performer_name = performer.get_full_name() or performer.username
    performer_email = performer.email
    base_url = getattr(settings, "MAGIC_LINK_BASE_URL", "")
    login_url = f"{base_url}/accounts/login/" if base_url else "/accounts/login/"

    subjects_and_bodies = {
        "CREATE": (
            "Your TRACE staff account has been created",
            f"Hi {name},\n\n"
            f"A TRACE staff account has been created for you by {performer_name} ({performer_email}).\n\n"
            f"Account details\n---------------\n"
            f"Username: {target_user.username}\n"
            f"Role:     {'Super User' if target_user.is_superuser else 'Admin'}\n"
            f"Sign-in:  {login_url}\n\n"
            + (f"Your initial password is: {password}\n\nYou should sign in and change your password as soon as possible.\n\n" if password else "")
            + f"If you were not expecting this email, reply to {performer_email} immediately.\n\n"
            "— TRACE, TISB Lost & Found"
        ),
        "PROMOTE_ADMIN": (
            "Your TRACE access has changed",
            f"Hi {name},\n\nyou have been granted Admin access to TRACE by {performer_name}. "
            f"You can now upload found items and access the Admin Dashboard. Sign in at {login_url}.\n\n"
            "— TRACE, TISB Lost & Found"
        ),
        "PROMOTE_SUPERUSER": (
            "Your TRACE access has changed",
            f"Hi {name},\n\nyou have been granted Super User access to TRACE by {performer_name}. "
            "You can now approve items, broadcast to the school, manage other users, and access "
            f"the Django admin. Sign in at {login_url}.\n\n"
            "— TRACE, TISB Lost & Found"
        ),
        "DEMOTE_TO_ADMIN": (
            "Your TRACE access has changed",
            f"Hi {name},\n\nyour access level on TRACE has been changed from Super User to Admin "
            f"by {performer_name}. You still have access to upload items and the Admin Dashboard, "
            "but you no longer have Super User powers (approvals, broadcasts, user management, "
            f"Django admin). If you have questions, contact {performer_email}.\n\n"
            "— TRACE, TISB Lost & Found"
        ),
        "REVOKE_STAFF": (
            "Your TRACE access has changed",
            f"Hi {name},\n\nyour staff access to TRACE has been revoked by {performer_name}. "
            "You can no longer upload items or access staff features. Your account still exists "
            f"but you will only see public pages when you sign in. If you have questions, contact {performer_email}.\n\n"
            "— TRACE, TISB Lost & Found"
        ),
        "DEACTIVATE": (
            "Your TRACE access has changed",
            f"Hi {name},\n\nyour TRACE account has been deactivated by {performer_name}. "
            f"You can no longer sign in. If this is unexpected, contact {performer_email}.\n\n"
            "— TRACE, TISB Lost & Found"
        ),
        "REACTIVATE": (
            "Your TRACE access has changed",
            f"Hi {name},\n\nyour TRACE account has been reactivated by {performer_name}. "
            f"You can now sign in again at {login_url}.\n\n"
            "— TRACE, TISB Lost & Found"
        ),
        "PASSWORD_RESET": (
            "Your TRACE password has been reset",
            f"Hi {name},\n\nYour TRACE password has been reset by {performer_name}.\n\n"
            + (f"Your new password is: {password}\n\nYou should sign in and change this password as soon as possible.\n\n" if password else f"Contact {performer_email} for your new password.\n\n")
            + f"If you did not request this, contact {performer_email} immediately.\n\n"
            "— TRACE, TISB Lost & Found"
        ),
    }

    entry = subjects_and_bodies.get(action)
    if entry and target_user.email:
        send_system_email(
            subject=entry[0],
            message=entry[1],
            recipient_list=[target_user.email],
        )


class UserManagementListView(LoginRequiredMixin, SuperUserRequiredMixin, ListView):
    """List all users with filtering and search (§6.7)."""
    template_name = "inventory/user_management/list.html"
    context_object_name = "users"
    paginate_by = 25

    def get_queryset(self):
        qs = User.objects.all().order_by("username")

        role_filter = self.request.GET.get("role", "")
        if role_filter == "superuser":
            qs = qs.filter(is_superuser=True, is_active=True)
        elif role_filter == "admin":
            qs = qs.filter(is_staff=True, is_superuser=False, is_active=True)
        elif role_filter == "deactivated":
            qs = qs.filter(is_active=False)
        elif role_filter == "no_staff":
            qs = qs.filter(is_staff=False, is_active=True)

        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(
                Q(username__icontains=q) | Q(first_name__icontains=q) |
                Q(last_name__icontains=q) | Q(email__icontains=q)
            )

        sort = self.request.GET.get("sort", "username")
        if sort == "last_login":
            qs = qs.order_by("-last_login")
        elif sort == "date_joined":
            qs = qs.order_by("-date_joined")
        elif sort == "role":
            qs = qs.order_by("-is_superuser", "-is_staff", "username")
        else:
            qs = qs.order_by("username")

        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["role_filter"] = self.request.GET.get("role", "")
        ctx["search_query"] = self.request.GET.get("q", "")
        ctx["current_sort"] = self.request.GET.get("sort", "username")
        # Annotate each user with their role string for the template
        for u in ctx["users"]:
            u.trace_role = _get_user_role(u)
        return ctx


class UserManagementCreateView(LoginRequiredMixin, SuperUserRequiredMixin, View):
    """Create a new staff user (§6.8)."""

    def get(self, request):
        form = UserCreateForm()
        return render(request, "inventory/user_management/create.html", {"form": form})

    def post(self, request):
        form = UserCreateForm(request.POST)
        if not form.is_valid():
            return render(request, "inventory/user_management/create.html", {"form": form})

        cd = form.cleaned_data
        role = cd["role"]
        is_staff = True
        is_superuser = role == "superuser"

        with transaction.atomic():
            user = User.objects.create_user(
                username=cd["username"],
                email=cd["email"],
                password=cd["password"],
                first_name=cd["first_name"],
                last_name=cd["last_name"],
                is_staff=is_staff,
                is_superuser=is_superuser,
                is_active=cd["is_active"],
            )
            UserProfile.objects.get_or_create(user=user)
            _log_role_change(
                user, request.user, "CREATE",
                details=f"Created with role={'Super User' if is_superuser else 'Admin'}; is_active={cd['is_active']}",
            )

        if cd.get("send_welcome_email"):
            _send_role_notification(user, request.user, "CREATE", password=cd["password"])

        role_label = "Super User" if is_superuser else "Admin"
        messages.success(request, f'User "{user.username}" created and granted {role_label} access.')
        return redirect("inventory:user_management_list")


class UserManagementDetailView(LoginRequiredMixin, SuperUserRequiredMixin, DetailView):
    """View one user's details and role-change history (§6.4)."""
    model = User
    template_name = "inventory/user_management/detail.html"
    context_object_name = "target_user"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["role_changes"] = UserRoleChangeLog.objects.filter(
            target_user=self.object
        ).select_related("performed_by").order_by("-created_at")[:20]
        ctx["user_role"] = _get_user_role(self.object)
        return ctx


class UserManagementEditView(LoginRequiredMixin, SuperUserRequiredMixin, View):
    """Edit an existing staff user (§6.9.1)."""

    def get(self, request, pk):
        target = get_object_or_404(User, pk=pk)
        form = UserEditForm(instance=target)
        return render(request, "inventory/user_management/edit.html", {
            "form": form, "target_user": target,
        })

    def post(self, request, pk):
        target = get_object_or_404(User, pk=pk)
        form = UserEditForm(request.POST, instance=target)
        if not form.is_valid():
            return render(request, "inventory/user_management/edit.html", {
                "form": form, "target_user": target,
            })

        cd = form.cleaned_data
        role = cd["role"]
        new_is_superuser = role == "superuser"
        new_is_staff = role in ("admin", "superuser")

        # §6.6 safeguards
        if target == request.user and (
            (target.is_superuser and not new_is_superuser) or
            (target.is_staff and not new_is_staff) or
            (target.is_active and not cd["is_active"])
        ):
            messages.error(request, "You cannot change your own role or status. Ask another Super User.")
            return redirect("inventory:user_management_edit", pk=pk)

        # Last super user protection
        if target.is_superuser and not new_is_superuser:
            if User.objects.filter(is_superuser=True, is_active=True).count() <= 1:
                messages.error(
                    request,
                    "This action would leave the system without any active Super Users. "
                    "Promote another user first.",
                )
                return redirect("inventory:user_management_edit", pk=pk)

        # Track changes for logging
        changes = []
        old_role = _get_user_role(target)

        with transaction.atomic():
            if target.first_name != cd["first_name"]:
                changes.append(f"first_name: {target.first_name!r} → {cd['first_name']!r}")
                target.first_name = cd["first_name"]
            if target.last_name != cd["last_name"]:
                changes.append(f"last_name: {target.last_name!r} → {cd['last_name']!r}")
                target.last_name = cd["last_name"]
            if target.email != cd["email"]:
                changes.append(f"email: {target.email!r} → {cd['email']!r}")
                target.email = cd["email"]
            if target.is_active != cd["is_active"]:
                changes.append(f"is_active: {target.is_active} → {cd['is_active']}")
                target.is_active = cd["is_active"]
            if target.is_staff != new_is_staff:
                changes.append(f"is_staff: {target.is_staff} → {new_is_staff}")
                target.is_staff = new_is_staff
            if target.is_superuser != new_is_superuser:
                changes.append(f"is_superuser: {target.is_superuser} → {new_is_superuser}")
                target.is_superuser = new_is_superuser
            target.save()

            new_role = _get_user_role(target)
            # Determine the right action log entry
            if old_role != new_role:
                action_map = {
                    ("no_staff", "admin"): "PROMOTE_ADMIN",
                    ("no_staff", "superuser"): "PROMOTE_SUPERUSER",
                    ("admin", "superuser"): "PROMOTE_SUPERUSER",
                    ("superuser", "admin"): "DEMOTE_TO_ADMIN",
                    ("superuser", "no_staff"): "REVOKE_STAFF",
                    ("admin", "no_staff"): "REVOKE_STAFF",
                }
                # Handle deactivation/reactivation specially
                if not cd["is_active"] and old_role != "deactivated":
                    action = "DEACTIVATE"
                elif cd["is_active"] and old_role == "deactivated":
                    action = "REACTIVATE"
                else:
                    action = action_map.get((old_role, new_role), "EDIT_PROFILE")
                _log_role_change(target, request.user, action, "; ".join(changes))
                _send_role_notification(target, request.user, action)
            elif changes:
                _log_role_change(target, request.user, "EDIT_PROFILE", "; ".join(changes))

        messages.success(request, f'User "{target.username}" updated.')
        return redirect("inventory:user_management_list")


class UserManagementSetPasswordView(LoginRequiredMixin, SuperUserRequiredMixin, View):
    """Set a user's password (§6.9.2)."""

    def get(self, request, pk):
        target = get_object_or_404(User, pk=pk)
        form = UserSetPasswordForm()
        return render(request, "inventory/user_management/set_password.html", {
            "form": form, "target_user": target,
        })

    def post(self, request, pk):
        target = get_object_or_404(User, pk=pk)
        form = UserSetPasswordForm(request.POST)
        if not form.is_valid():
            return render(request, "inventory/user_management/set_password.html", {
                "form": form, "target_user": target,
            })

        cd = form.cleaned_data
        with transaction.atomic():
            target.set_password(cd["password"])
            target.save()
            _log_role_change(target, request.user, "PASSWORD_RESET")

        if cd.get("send_email"):
            _send_role_notification(target, request.user, "PASSWORD_RESET", password=cd["password"])

        messages.success(request, f'Password updated for "{target.username}".')
        return redirect("inventory:user_management_detail", pk=pk)


class UserManagementDeleteView(LoginRequiredMixin, SuperUserRequiredMixin, View):
    """Delete a user with safeguards (§6.9.3)."""

    def get(self, request, pk):
        target = get_object_or_404(User, pk=pk)
        return render(request, "inventory/user_management/delete.html", {"target_user": target})

    def post(self, request, pk):
        target = get_object_or_404(User, pk=pk)

        # §6.6 safeguards
        if target == request.user:
            messages.error(request, "You cannot delete your own account.")
            return redirect("inventory:user_management_list")

        if target.is_superuser and target.is_active:
            if User.objects.filter(is_superuser=True, is_active=True).count() <= 1:
                messages.error(
                    request,
                    "This action would leave the system without any active Super Users. "
                    "Promote another user first.",
                )
                return redirect("inventory:user_management_list")

        # Username confirmation (§6.9.3)
        confirm_username = request.POST.get("confirm_username", "").strip()
        if confirm_username != target.username:
            messages.error(request, "Username confirmation did not match. Deletion cancelled.")
            return redirect("inventory:user_management_delete", pk=pk)

        with transaction.atomic():
            _log_role_change(target, request.user, "DELETE",
                             details=f"User deleted: {target.username} ({target.email})")
            username = target.username
            target.delete()

        messages.success(request, f'User "{username}" has been permanently deleted.')
        return redirect("inventory:user_management_list")


class UserRoleChangeHistoryView(LoginRequiredMixin, SuperUserRequiredMixin, ListView):
    """Audit log of all role changes (§6.12)."""
    model = UserRoleChangeLog
    template_name = "inventory/user_management/role_change_history.html"
    context_object_name = "changes"
    paginate_by = 50

    def get_queryset(self):
        qs = UserRoleChangeLog.objects.select_related("target_user", "performed_by")
        action = self.request.GET.get("action")
        if action:
            qs = qs.filter(action=action)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["action_choices"] = UserRoleChangeLog.ACTION_CHOICES
        return ctx

