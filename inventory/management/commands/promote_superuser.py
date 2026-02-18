from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from inventory.models import UserProfile

User = get_user_model()


class Command(BaseCommand):
    help = 'Promote a user to Super User status for the Lost & Found system'

    def add_arguments(self, parser):
        parser.add_argument(
            'username',
            type=str,
            help='Username of the user to promote to Super User',
        )

    def handle(self, *args, **options):
        username = options['username']
        
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(f'User "{username}" does not exist.')
            )
            return
        
        # Ensure user is staff
        if not user.is_staff:
            user.is_staff = True
            user.save()
            self.stdout.write(
                self.style.WARNING(f'User "{username}" was not staff. Set is_staff=True.')
            )
        
        # Get or create UserProfile
        profile, created = UserProfile.objects.get_or_create(user=user)
        if profile.is_super_user:
            self.stdout.write(
                self.style.WARNING(f'User "{username}" is already a Super User.')
            )
        else:
            profile.is_super_user = True
            profile.save()
            self.stdout.write(
                self.style.SUCCESS(
                    f'Successfully promoted "{username}" to Super User status.'
                )
            )

