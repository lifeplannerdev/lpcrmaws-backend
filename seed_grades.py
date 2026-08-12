from students.models import AcademicGrade
AcademicGrade.objects.get_or_create(name='A1', order=1)
AcademicGrade.objects.get_or_create(name='A2', order=2)
AcademicGrade.objects.get_or_create(name='B1', order=3)
AcademicGrade.objects.get_or_create(name='B2', order=4)
print('Grades seeded.')
