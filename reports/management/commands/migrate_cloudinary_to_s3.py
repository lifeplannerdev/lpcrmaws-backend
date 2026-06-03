import os
import requests
from django.core.management.base import BaseCommand
from django.core.files.base import ContentFile
from reports.models import DailyReportAttachment
from hr.models import AttendanceDocument, Asset, Candidate
from chats.models import Message
import cloudinary
import cloudinary.api

class Command(BaseCommand):
    help = 'Migrates existing files from Cloudinary to AWS S3.'

    def add_arguments(self, parser):
        parser.add_argument('--cloud-name', type=str, required=True, help='Cloudinary cloud name')
        parser.add_argument('--api-key', type=str, required=True, help='Cloudinary API key')
        parser.add_argument('--api-secret', type=str, required=True, help='Cloudinary API secret')

    def download_and_save(self, instance, field_name, api_key, api_secret, cloud_name):
        field_attr = getattr(instance, field_name)
        
        # If no file exists, skip
        if not field_attr or not str(field_attr):
            return

        # Check if it's already an S3 URL or doesn't look like Cloudinary
        file_path_or_url = str(field_attr)
        if 'amazonaws.com' in file_path_or_url or not '/' in file_path_or_url:
            self.stdout.write(self.style.WARNING(f"Skipping ID {instance.id}: Already migrated or not a valid path ({file_path_or_url})"))
            return

        # Using cloudinary SDK to get the URL
        try:
            url, options = cloudinary.utils.cloudinary_url(file_path_or_url)
            # Ensure it's HTTPS
            if url.startswith('http://'):
                url = url.replace('http://', 'https://')
                
            self.stdout.write(f"Downloading {url}...")
            
            response = requests.get(url, stream=True, timeout=30)
            response.raise_for_status()

            # Determine original filename
            original_filename = getattr(instance, 'original_filename', None)
            if not original_filename:
                # Extract filename from URL
                original_filename = url.split('/')[-1]
                if '?' in original_filename:
                    original_filename = original_filename.split('?')[0]
                
                # Some public IDs might not have extensions, so this is a fallback
                if not '.' in original_filename:
                    original_filename += '.bin'
                    
            # Safe filename
            safe_filename = original_filename.replace(' ', '_')
            
            # Save to S3 using the field
            field_attr.save(safe_filename, ContentFile(response.content), save=True)
            self.stdout.write(self.style.SUCCESS(f"Successfully migrated ID {instance.id} to {field_attr.name}"))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Failed to migrate ID {instance.id}: {e}"))


    def handle(self, *args, **options):
        cloud_name = options['cloud_name']
        api_key = options['api_key']
        api_secret = options['api_secret']

        cloudinary.config(
            cloud_name=cloud_name,
            api_key=api_key,
            api_secret=api_secret
        )

        self.stdout.write(self.style.SUCCESS(f"Starting migration to S3..."))

        # DailyReportAttachment
        attachments = DailyReportAttachment.objects.exclude(attached_file='').exclude(attached_file__isnull=True)
        self.stdout.write(f"\nProcessing {attachments.count()} DailyReportAttachments...")
        for att in attachments:
            self.download_and_save(att, 'attached_file', api_key, api_secret, cloud_name)

        # HR AttendanceDocument
        attendances = AttendanceDocument.objects.exclude(document='').exclude(document__isnull=True)
        self.stdout.write(f"\nProcessing {attendances.count()} AttendanceDocuments...")
        for att in attendances:
            self.download_and_save(att, 'document', api_key, api_secret, cloud_name)

        # HR Asset
        assets = Asset.objects.exclude(attachment='').exclude(attachment__isnull=True)
        self.stdout.write(f"\nProcessing {assets.count()} Assets...")
        for asset in assets:
            self.download_and_save(asset, 'attachment', api_key, api_secret, cloud_name)

        # HR Candidate
        candidates = Candidate.objects.exclude(resume='').exclude(resume__isnull=True)
        self.stdout.write(f"\nProcessing {candidates.count()} Candidates...")
        for cand in candidates:
            self.download_and_save(cand, 'resume', api_key, api_secret, cloud_name)

        # Chats Message
        messages = Message.objects.exclude(file='').exclude(file__isnull=True)
        self.stdout.write(f"\nProcessing {messages.count()} Messages...")
        for msg in messages:
            self.download_and_save(msg, 'file', api_key, api_secret, cloud_name)

        self.stdout.write(self.style.SUCCESS("Migration complete!"))
