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
from .models import Item
from .services import analyze_item_images


class StaffRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        user = self.request.user
        return user.is_authenticated and user.is_staff


class LandingPageView(TemplateView):
    template_name = "inventory/landing.html"


class ItemUploadView(LoginRequiredMixin, StaffRequiredMixin, View):
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
        item.save()
        
        # Only save formset if there are images
        formset.instance = item
        if formset.has_changed():
            formset.save()

        messages.success(
            request,
            f'Item "{item.title}" has been successfully uploaded!',
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
        
        # Combine FOUND items and CLAIMED items within duration
        queryset = Item.objects.filter(
            Q(status=Item.Status.FOUND) | claimed_q_objects
        ).prefetch_related('images')

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


class ClaimItemView(View):
    """Handle item claiming - marks item as CLAIMED and captures claimant name."""
    http_method_names = ["post"]
    
    def post(self, request, pk):
        item = get_object_or_404(Item, pk=pk)
        form = ClaimItemForm(request.POST)
        
        if form.is_valid() and item.status == Item.Status.FOUND:
            name = form.cleaned_data['name']
            item.status = Item.Status.CLAIMED
            item.claimed_by_name = name
            item.claimed_at = timezone.now()
            item.save()
            
            # Success message for the user claiming the item
            messages.success(
                request,
                'Item successfully claimed! Pick it up from the reception.',
            )
            
            # Also log for admin visibility
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"Item '{item.title}' (ID: {item.pk}) claimed by {name} at {item.claimed_at}")
            
        elif not form.is_valid():
            # If form is invalid, show errors
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
        
        return redirect("inventory:item_detail", pk=pk)


class AdminDashboardView(LoginRequiredMixin, StaffRequiredMixin, View):
    """Admin dashboard showing all items in a table with claim information."""
    template_name = "inventory/admin_dashboard.html"
    paginate_by = 50

    def get(self, request):
        from django.core.paginator import Paginator
        
        # Get all items
        items = Item.objects.all().prefetch_related('images').order_by('-date_found', '-created_at')
        
        # Paginate
        paginator = Paginator(items, self.paginate_by)
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)
        
        # Get all claimed items for notification messages
        claimed_items = Item.objects.filter(
            status=Item.Status.CLAIMED,
            claimed_at__isnull=False
        ).order_by('-claimed_at')
        
        # Create claim messages (stored in session to persist until dismissed)
        claim_messages = request.session.get('claim_messages', [])
        
        # Add new claims that aren't in the session yet
        for item in claimed_items:
            if item.claimed_by_name and item.claimed_at:
                message_id = f"claim_{item.pk}_{item.claimed_at.timestamp()}"
                if not any(msg['id'] == message_id for msg in claim_messages):
                    claim_messages.append({
                        'id': message_id,
                        'item_title': item.title,
                        'claimant_name': item.claimed_by_name,
                        'claimed_at': item.claimed_at.isoformat(),  # Convert datetime to string for JSON serialization
                    })
        
        # Store updated messages in session
        request.session['claim_messages'] = claim_messages
        
        # Count claims per item for row coloring
        # For now, we only have one claim per item, but structure allows for multiple
        items_with_multiple_claims = set()
        for item in page_obj:
            # Currently only one claim per item, but this can be extended
            # For now, no items will have multiple claims, but this structure allows for it
            claim_count = 1 if item.status == Item.Status.CLAIMED and item.claimed_by_name else 0
            if claim_count > 1:
                items_with_multiple_claims.add(item.pk)
        
        context = {
            'items': page_obj,
            'page_obj': page_obj,
            'is_paginated': page_obj.has_other_pages(),
            'claim_messages': claim_messages,
            'items_with_multiple_claims': items_with_multiple_claims,
        }
        
        return render(request, self.template_name, context)

    def post(self, request):
        """Handle message dismissal."""
        import json
        try:
            data = json.loads(request.body)
            if data.get('action') == 'dismiss_message':
                message_id = data.get('message_id')
                claim_messages = request.session.get('claim_messages', [])
                claim_messages = [msg for msg in claim_messages if msg['id'] != message_id]
                request.session['claim_messages'] = claim_messages
                return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=400)
        
        return JsonResponse({'success': False}, status=400)

