from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.views.generic import DetailView, ListView, TemplateView

from .forms import ClaimItemForm, ItemForm, ItemImageFormSet
from .models import Item, UserProfile, StudentLostItem
from .services import analyze_item_images


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
    """Handle item claiming - allows multiple people to claim the same item."""
    http_method_names = ["post"]
    
    def post(self, request, pk):
        from .models import Claim
        
        item = get_object_or_404(Item, pk=pk)
        form = ClaimItemForm(request.POST)
        
        if form.is_valid():
            name = form.cleaned_data['name']
            
            # Create a new claim (allows multiple claims per item)
            claim = Claim.objects.create(
                item=item,
                claimant_name=name,
            )
            
            # Update item status to CLAIMED if it's the first claim
            if item.status == Item.Status.FOUND:
                item.status = Item.Status.CLAIMED
                # Keep backward compatibility with old fields
                item.claimed_by_name = name
                item.claimed_at = timezone.now()
                item.save()
            
            # Success message for the user claiming the item
            if item.claim_count > 1:
                messages.success(
                    request,
                    f'Item successfully claimed! Note: {item.claim_count} people have claimed this item. Pick it up from the reception.',
                )
            else:
                messages.success(
                    request,
                    'Item successfully claimed! Pick it up from the reception.',
                )
            
            # Also log for admin visibility
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"Item '{item.title}' (ID: {item.pk}) claimed by {name} at {claim.claimed_at}")
            
        elif not form.is_valid():
            # If form is invalid, show errors
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
        
        return redirect("inventory:item_detail", pk=pk)


class AdminDashboardView(LoginRequiredMixin, AdminOrSuperUserRequiredMixin, View):
    """Admin dashboard showing all items in a table with claim information."""
    template_name = "inventory/admin_dashboard.html"
    paginate_by = 50

    def get(self, request):
        from django.core.paginator import Paginator
        
        # Get all items with claims prefetched
        items = Item.objects.all().prefetch_related('images', 'claims').order_by('-date_found', '-created_at')
        
        # Paginate
        paginator = Paginator(items, self.paginate_by)
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)
        
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
            # Use the claim_count property from the model
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
    """Approval queue for Super Users to approve/reject pending items."""
    template_name = "inventory/approval_queue.html"
    context_object_name = "pending_items"
    paginate_by = 20

    def get_queryset(self):
        # Get all pending items (both Item and StudentLostItem)
        pending_items = []
        
        # Pending admin-uploaded items
        admin_items = Item.objects.filter(
            approval_status=Item.ApprovalStatus.PENDING
        ).prefetch_related('images', 'created_by').order_by('-created_at')
        
        for item in admin_items:
            pending_items.append({
                'type': 'admin_item',
                'item': item,
                'item_type_display': item.get_item_type_display(),
            })
        
        # Pending student-submitted items
        student_items = StudentLostItem.objects.filter(
            approval_status=StudentLostItem.ApprovalStatus.PENDING
        ).prefetch_related('images').order_by('-submitted_at')
        
        for item in student_items:
            pending_items.append({
                'type': 'student_item',
                'item': item,
            })
        
        # Sort by creation/submission date (most recent first)
        pending_items.sort(key=lambda x: (
            x['item'].created_at if hasattr(x['item'], 'created_at') else x['item'].submitted_at
        ), reverse=True)
        
        return pending_items

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Count pending items by type
        context['pending_admin_items_count'] = Item.objects.filter(
            approval_status=Item.ApprovalStatus.PENDING
        ).count()
        context['pending_student_items_count'] = StudentLostItem.objects.filter(
            approval_status=StudentLostItem.ApprovalStatus.PENDING
        ).count()
        return context


class ApproveItemView(LoginRequiredMixin, SuperUserRequiredMixin, View):
    """Approve a pending item (either Item or StudentLostItem)."""
    
    def post(self, request, item_type, item_id):
        if item_type == 'admin':
            item = get_object_or_404(Item, pk=item_id, approval_status=Item.ApprovalStatus.PENDING)
            item.approval_status = Item.ApprovalStatus.APPROVED
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
            messages.success(request, f'Student lost item "{item.title}" has been approved!')
            return redirect('inventory:approval_queue')
        else:
            messages.error(request, 'Invalid item type.')
            return redirect('inventory:approval_queue')


class RejectItemView(LoginRequiredMixin, SuperUserRequiredMixin, View):
    """Reject a pending item (either Item or StudentLostItem)."""
    
    def post(self, request, item_type, item_id):
        if item_type == 'admin':
            item = get_object_or_404(Item, pk=item_id, approval_status=Item.ApprovalStatus.PENDING)
            item.approval_status = Item.ApprovalStatus.REJECTED
            item.save()
            messages.success(request, f'Item "{item.title}" has been rejected.')
            return redirect('inventory:approval_queue')
        elif item_type == 'student':
            item = get_object_or_404(
                StudentLostItem,
                pk=item_id,
                approval_status=StudentLostItem.ApprovalStatus.PENDING
            )
            item.approval_status = StudentLostItem.ApprovalStatus.REJECTED
            item.approved_by = request.user
            item.approved_at = timezone.now()
            item.save()
            messages.success(request, f'Student lost item "{item.title}" has been rejected.')
            return redirect('inventory:approval_queue')
        else:
            messages.error(request, 'Invalid item type.')
            return redirect('inventory:approval_queue')

