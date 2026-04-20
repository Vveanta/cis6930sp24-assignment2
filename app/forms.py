from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, FileField, RadioField, MultipleFileField, TextAreaField, EmailField, SelectMultipleField, SelectField
from wtforms.validators import DataRequired, URL, Email, ValidationError


class URLForm(FlaskForm):
    url = StringField('Enter URL of PDF', validators=[DataRequired(), URL()])
    submit = SubmitField('Submit')


class ConditionalDataRequired(DataRequired):
    def __init__(self, exclude_values=('default_pdf',), *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.exclude_values = exclude_values if isinstance(exclude_values, (list, tuple)) else (exclude_values,)

    def __call__(self, form, field):
        if form.file_type.data not in self.exclude_values:
            super().__call__(form, field)


class UploadForm(FlaskForm):
    file_type = RadioField(
        'File Type',
        choices=[
            ('csv', 'CSV'),
            ('pdf', 'PDF'),
            ('url', 'URL'),
            ('default_pdf', 'Default PDF'),
            ('norman_daily', 'Norman daily reports (pick dates)'),
        ],
        validators=[DataRequired()],
    )
    file = MultipleFileField(
        'File',
        validators=[
            ConditionalDataRequired(
                exclude_values=('default_pdf', 'norman_daily'),
                message='File is required for this option',
            )
        ],
    )
    default_pdfs = SelectField('Default PDF Files', choices=[])
    submit = SubmitField('Process')


class FeedbackForm(FlaskForm):
    name = StringField('Full name', validators=[DataRequired()])
    email = EmailField('Email', validators=[DataRequired(), Email()])
    user_type = RadioField(
        'Which Describes you the Best',
        choices=[('student', 'Student'), ('professor', 'Professor'), ('recruiter', 'Corporate Recruiter'), ('other', 'Other')],
        validators=[DataRequired()],
    )
    rating = RadioField(
        'Rate Your Experience',
        choices=[('1', '1 - Very Poor'), ('2', '2 - Poor'), ('3', '3 - Average'), ('4', '4 - Good'), ('5', '5 - Excellent')],
        validators=[DataRequired()],
    )
    feedback = TextAreaField('Your Feedback', validators=[DataRequired()])
    submit = SubmitField('Submit Feedback')
