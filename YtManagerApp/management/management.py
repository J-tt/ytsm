from apscheduler.schedulers.background import BackgroundScheduler

from YtManagerApp.models import SubscriptionFolder, Subscription, Video, Channel
from YtManagerApp.utils.youtube import YoutubeAPI, YoutubeChannelInfo


class FolderManager(object):

    @staticmethod
    def create_or_edit(fid, name, parent_id):
        # Create or edit
        if fid == '#':
            folder = SubscriptionFolder()
        else:
            folder = SubscriptionFolder.objects.get(id=int(fid))

        # Set attributes
        folder.name = name
        if parent_id == '#':
            folder.parent = None
        else:
            folder.parent = SubscriptionFolder.objects.get(id=int(parent_id))

        FolderManager.__validate(folder)
        folder.save()

    @staticmethod
    def __validate(folder: SubscriptionFolder):
        # Make sure folder name is unique in the parent folder
        for dbFolder in SubscriptionFolder.objects.filter(parent_id=folder.parent_id):
            if dbFolder.id != folder.id and dbFolder.name == folder.name:
                raise ValueError('Folder name is not unique!')

        # Prevent parenting loops
        current = folder
        visited = []

        while not (current is None):
            if current in visited:
                raise ValueError('Parenting cycle detected!')
            visited.append(current)
            current = current.parent

    @staticmethod
    def delete(fid: int):
        folder = SubscriptionFolder.objects.get(id=fid)
        folder.delete()

    @staticmethod
    def list_videos(fid: int):
        folder = SubscriptionFolder.objects.get(id=fid)
        folder_list = []
        queue = [folder]
        while len(queue) > 0:
            folder = queue.pop()
            folder_list.append(folder)
            queue.extend(SubscriptionFolder.objects.filter(parent=folder))

        return Video.objects.filter(subscription__parent_folder__in=folder_list).order_by('-publish_date')


class SubscriptionManager(object):
    __scheduler = BackgroundScheduler()

    @staticmethod
    def create_or_edit(sid, url, name, parent_id):
        # Create or edit
        if sid == '#':
            SubscriptionManager.create(url, parent_id, YoutubeAPI.build_public())
        else:
            sub = Subscription.objects.get(id=int(sid))
            sub.name = name

            if parent_id == '#':
                sub.parent_folder = None
            else:
                sub.parent_folder = SubscriptionFolder.objects.get(id=int(parent_id))

            sub.save()

    @staticmethod
    def create(url, parent_id, yt_api: YoutubeAPI):
        sub = Subscription()
        # Set parent
        if parent_id == '#':
            sub.parent_folder = None
        else:
            sub.parent_folder = SubscriptionFolder.objects.get(id=int(parent_id))

        # Pull information about the channel and playlist
        url_type, url_id = yt_api.parse_channel_url(url)

        if url_type == 'playlist_id':
            info_playlist = yt_api.get_playlist_info(url_id)
            channel = SubscriptionManager.__get_or_create_channel('channel_id', info_playlist.getChannelId(), yt_api)
            sub.name = info_playlist.getTitle()
            sub.playlist_id = info_playlist.getId()
            sub.description = info_playlist.getDescription()
            sub.channel = channel
            sub.icon_default = info_playlist.getDefaultThumbnailUrl()
            sub.icon_best = info_playlist.getBestThumbnailUrl()

        else:
            channel = SubscriptionManager.__get_or_create_channel(url_type, url_id, yt_api)
            # No point in getting the 'uploads' playlist info
            sub.name = channel.name
            sub.playlist_id = channel.upload_playlist_id
            sub.description = channel.description
            sub.channel = channel
            sub.icon_default = channel.icon_default
            sub.icon_best = channel.icon_best

        sub.save()

