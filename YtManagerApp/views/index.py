from django.http import HttpRequest, HttpResponseBadRequest, JsonResponse
from django.shortcuts import render
from django import forms
from django.views.generic import CreateView, UpdateView, DeleteView
from YtManagerApp.management.folders import traverse_tree
from YtManagerApp.management.videos import get_videos
from YtManagerApp.models import Subscription, SubscriptionFolder
from YtManagerApp.views.controls.modal import ModalMixin
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Field
from crispy_forms.layout import Submit
from django.db.models import Q


class VideoFilterForm(forms.Form):
    CHOICES_SORT = (
        ('newest', 'Newest'),
        ('oldest', 'Oldest'),
        ('playlist', 'Playlist order'),
        ('playlist_reverse', 'Reverse playlist order'),
        ('popularity', 'Popularity'),
        ('rating', 'Top rated'),
    )

    # Map select values to actual column names
    MAPPING_SORT = {
        'newest': '-publish_date',
        'oldest': 'publish_date',
        'playlist': 'playlist_index',
        'playlist_reverse': '-playlist_index',
        'popularity': '-views',
        'rating': '-rating'
    }

    CHOICES_SHOW_WATCHED = (
        ('y', 'Watched'),
        ('n', 'Not watched'),
        ('all', '(All)')
    )

    CHOICES_SHOW_DOWNLOADED = (
        ('y', 'Downloaded'),
        ('n', 'Not downloaded'),
        ('all', '(All)')
    )

    MAPPING_SHOW = {
        'y': True,
        'n': False,
        'all': None
    }

    query = forms.CharField(label='', required=False)
    sort = forms.ChoiceField(label='Sort:', choices=CHOICES_SORT, initial='newest')
    show_watched = forms.ChoiceField(label='Show only: ', choices=CHOICES_SHOW_WATCHED, initial='all')
    show_downloaded = forms.ChoiceField(label='', choices=CHOICES_SHOW_DOWNLOADED, initial='all')
    subscription_id = forms.IntegerField(
        required=False,
        widget=forms.HiddenInput()
    )
    folder_id = forms.IntegerField(
        required=False,
        widget=forms.HiddenInput()
    )

    def __init__(self, data=None):
        super().__init__(data, auto_id='form_video_filter_%s')
        self.helper = FormHelper()
        self.helper.form_id = 'form_video_filter'
        self.helper.form_class = 'form-inline'
        self.helper.form_method = 'POST'
        self.helper.form_action = 'ajax_index_get_videos'
        self.helper.field_class = 'mr-1'
        self.helper.label_class = 'ml-2 mr-1 no-asterisk'

        self.helper.layout = Layout(
            Field('query', placeholder='Search'),
            'sort',
            'show_watched',
            'show_downloaded',
            'subscription_id',
            'folder_id'
        )

    def clean_sort(self):
        data = self.cleaned_data['sort']
        return VideoFilterForm.MAPPING_SORT[data]

    def clean_show_downloaded(self):
        data = self.cleaned_data['show_downloaded']
        return VideoFilterForm.MAPPING_SHOW[data]

    def clean_show_watched(self):
        data = self.cleaned_data['show_watched']
        return VideoFilterForm.MAPPING_SHOW[data]


def __tree_folder_id(fd_id):
    if fd_id is None:
        return '#'
    return 'folder' + str(fd_id)


def __tree_sub_id(sub_id):
    if sub_id is None:
        return '#'
    return 'folder' + str(sub_id)


def index(request: HttpRequest):
    if request.user.is_authenticated:
        context = {
            'filter_form': VideoFilterForm()
        }
        return render(request, 'YtManagerApp/index.html', context)
    else:
        return render(request, 'YtManagerApp/index_unauthenticated.html')


def ajax_get_tree(request: HttpRequest):

    def visit(node):
        if isinstance(node, SubscriptionFolder):
            return {
                "id": __tree_folder_id(node.id),
                "text": node.name,
                "type": "folder",
                "state": {"opened": True},
                "parent": __tree_folder_id(node.parent_id)
            }
        elif isinstance(node, Subscription):
            return {
                "id": __tree_sub_id(node.id),
                "type": "sub",
                "text": node.name,
                "icon": node.icon_default,
                "parent": __tree_folder_id(node.parent_folder_id)
            }

    result = traverse_tree(None, request.user, visit)
    return JsonResponse(result, safe=False)


def ajax_get_videos(request: HttpRequest):
    if request.method == 'POST':
        form = VideoFilterForm(request.POST)
        if form.is_valid():
            videos = get_videos(
                user=request.user,
                sort_order=form.cleaned_data['sort'],
                query=form.cleaned_data['query'],
                subscription_id=form.cleaned_data['subscription_id'],
                folder_id=form.cleaned_data['folder_id'],
                only_watched=form.cleaned_data['show_watched'],
                only_downloaded=form.cleaned_data['show_downloaded']
            )

            context = {
                'videos': videos
            }

            return render(request, 'YtManagerApp/index_videos.html', context)

    return HttpResponseBadRequest()


class SubscriptionFolderForm(forms.ModelForm):
    class Meta:
        model = SubscriptionFolder
        fields = ['name', 'parent']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_tag = False

    def clean_name(self):
        name = self.cleaned_data['name']
        return name.strip()

    def clean(self):
        cleaned_data = super().clean()
        name = cleaned_data.get('name')
        parent = cleaned_data.get('parent')

        # Check name is unique in parent folder
        args_id = []
        if self.instance is not None:
            args_id.append(~Q(id=self.instance.id))

        if SubscriptionFolder.objects.filter(parent=parent, name__iexact=name, *args_id).count() > 0:
            raise forms.ValidationError('A folder with the same name already exists in the given parent directory!', code='already_exists')

        # Check for cycles
        if self.instance is not None:
            self.__test_cycles(parent)

    def __test_cycles(self, new_parent):
        visited = [self.instance.id]
        current = new_parent
        while current is not None:
            if current.id in visited:
                raise forms.ValidationError('Selected parent would create a parenting cycle!', code='parenting_cycle')
            visited.append(current.id)
            current = current.parent


class CreateFolderModal(ModalMixin, CreateView):
    template_name = 'YtManagerApp/controls/folder_create_modal.html'
    form_class = SubscriptionFolderForm

    def form_valid(self, form):
        form.instance.user = self.request.user
        return super().form_valid(form)


class UpdateFolderModal(ModalMixin, UpdateView):
    template_name = 'YtManagerApp/controls/folder_update_modal.html'
    model = SubscriptionFolder
    form_class = SubscriptionFolderForm


class DeleteFolderModal(ModalMixin, DeleteView):
    template_name = 'YtManagerApp/controls/folder_delete_modal.html'
    model = SubscriptionFolder