from leads.models import Lead
for f in Lead._meta.fields:
    print(f.name)
