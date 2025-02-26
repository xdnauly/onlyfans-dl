#!/usr/bin/python3
#
# OnlyFans Profile Downloader/Archiver
# KORNHOLIO 2020
#
# See README for help/info.
#
# This program is Free Software, licensed under the
# terms of GPLv3. See LICENSE.txt for details.

import asyncio
import pathlib
import re
import os
import sys
import json
import shutil
import time
import datetime as dt
import hashlib
import requests
import httpx
import pretty_errors

from typing import Any, Set

# maximum number of posts to index
# DONT CHANGE THAT
POST_LIMIT = 100

# api info
URL = "https://onlyfans.com"
API_URL = "/api2/v2"

# \TODO dynamically get app token
# Note: this is not an auth token
APP_TOKEN = "33d57ade8c02dbc5a333db99ff9ae26a"

# user info from /users/customer
USER_INFO: dict[str, Any] = {}

# target profile
PROFILE = ""
# profile data from /users/<profile>
PROFILE_INFO: dict[str, Any] = {}
PROFILE_ID = ""

# async
DOWNLOAD_LIMIT = 8

EXIST_POST: Set[str] = set()


# helper function to make sure a dir is present
def assure_dir(path: str) -> None:
    if not os.path.isdir(path):
        os.mkdir(path)

# Create Auth with Json
def create_auth() -> dict[str, str]:
    if os.path.exists('my_auth.json'):
        with open("my_auth.json") as f:
            ljson = json.load(f)
    else:
        with open("auth.json") as f:
            ljson = json.load(f)

    return {
        "Accept": "application/json, text/plain, */*",
        "User-Agent": ljson["user-agent"],
        "Accept-Encoding": "gzip, deflate",
        "user-id": ljson["user-id"],
        "x-bc": ljson["x-bc"],
        "Cookie": "sess=" + ljson["sess"],
        "app-token": APP_TOKEN
    }


# Every API request must be signed
def create_signed_headers(link: str, queryParams: dict[str, str]) -> None:

    global API_HEADER
    path = "/api2/v2" + link
    if (queryParams):
        query = '&'.join('='.join((key, val))
                         for (key, val) in queryParams.items())
        path = f"{path}?{query}"
    unixtime = str(int(dt.datetime.now().timestamp()))
    msg = "\n".join([dynamic_rules["static_param"],
                    unixtime, path, API_HEADER["user-id"]])
    message = msg.encode("utf-8")
    hash_object = hashlib.sha1(message)
    sha_1_sign = hash_object.hexdigest()
    sha_1_b = sha_1_sign.encode("ascii")
    checksum = sum([sha_1_b[number] for number in dynamic_rules["checksum_indexes"]]
                   ) + dynamic_rules["checksum_constant"]
    API_HEADER["sign"] = dynamic_rules["format"].format(
        sha_1_sign, abs(checksum))
    API_HEADER["time"] = unixtime

    return


# API request convenience function
# getdata and postdata should both be JSON
def api_request(endpoint: str, getdata: dict[str, str] | None = None, postdata: dict[str, str] | None = None, getparams=None):
    if getparams == None:
        getparams = {
            "order": "publish_date_desc"
        }
    if getdata is not None:
        for i in getdata:
            getparams[i] = getdata[i]

    if postdata is None:
        if getdata is not None:
            # Fixed the issue with the maximum limit of 10 posts by creating a kind of "pagination"

            create_signed_headers(endpoint, getparams)
            list_base = requests.get(URL + API_URL + endpoint,
                                     headers=API_HEADER,
                                     params=getparams,
                                     ).json()
            posts_num = len(list_base)

            if posts_num >= POST_LIMIT:
                beforePublishTime = list_base[POST_LIMIT -
                                              1]['postedAtPrecise']
                getparams['beforePublishTime'] = beforePublishTime

                while posts_num == POST_LIMIT:
                    # Extract posts
                    create_signed_headers(endpoint, getparams)
                    list_extend = requests.get(URL + API_URL + endpoint,
                                               headers=API_HEADER,
                                               params=getparams,
                                               ).json()
                    posts_num = len(list_extend)
                    # Merge with previous posts
                    list_base.extend(list_extend)

                    if posts_num < POST_LIMIT:
                        break

                    # Re-add again the updated beforePublishTime/postedAtPrecise params
                    beforePublishTime = list_extend[posts_num -
                                                    1]['postedAtPrecise']
                    getparams['beforePublishTime'] = beforePublishTime

            return list_base
        else:
            create_signed_headers(endpoint, getparams)
            print('x')
            return requests.get(URL + API_URL + endpoint,
                                headers=API_HEADER,
                                params=getparams,
                                )
    else:
        create_signed_headers(endpoint, getparams)
        return requests.post(URL + API_URL + endpoint,
                             headers=API_HEADER,
                             params=getparams,
                             data=postdata,
                             )


# /users/<profile>
# get information about <profile>
# <profile> = "customer" -> info about yourself
def get_user_info(profile: str) -> dict[str, str]:
    info = api_request("/users/" + profile).json()
    if "error" in info:
        print("\nERROR: " + info["error"]["message"])
        # bail, we need info for both profiles to be correct
        exit()
    return info

# to get subscribesCount for displaying all subs
# info about yourself


def user_me() -> dict:
    me = api_request("/users/me").json()
    if "error" in me:
        print("\nERROR: " + me["error"]["message"])
        # bail, we need info for both profiles to be correct
        exit()
    return me

# get all subscriptions in json


def get_subs() -> list[dict]:
    SUB_LIMIT = str(user_me()["subscribesCount"])
    params = {
        "type": "active",
        "sort": "desc",
        "field": "expire_date",
        "limit": SUB_LIMIT
    }
    return api_request("/subscriptions/subscribes", getparams=params).json()


# download public files like avatar and header
new_files = 0
tasks: list = []


def select_sub() -> list[Any]:
    # Get Subscriptions
    SUBS = get_subs()
    sub_dict.update({"0": "*** Download All Models ***"})
    ALL_LIST = []
    for i in range(1, len(SUBS)+1):
        ALL_LIST.append(i)
    for i in range(0, len(SUBS)):
        sub_dict.update({i+1: SUBS[i]["username"]})
    if len(sub_dict) == 1:
        print('No models subbed')
        exit()

    # Select Model
    if ARG1 == "all":
        return ALL_LIST
    MODELS = str((input('\n'.join('{} | {}'.format(key, value) for key,
                 value in sub_dict.items()) + "\nEnter number to download model\n")))
    if MODELS == "0":
        return ALL_LIST
    else:
        return [x.strip() for x in MODELS.split(',')]


def download_public_files() -> None:
    public_files = ["avatar", "header"]
    for public_file in public_files:
        source = PROFILE_INFO[public_file]
        if source is None:
            continue
        id = get_id_from_path(source)
        file_type = re.findall("\.\w+", source)[-1]
        path = "/" + public_file + "/" + id + file_type
        if not os.path.isfile("profiles/" + PROFILE + path):
            print("Downloading " + public_file + "...")
            download_file(PROFILE_INFO[public_file], path)
            global new_files
            new_files += 1


# download a media item and save it to the relevant directory
def download_media(media: dict[str, Any], is_archived: bool):
    id = str(media["id"])
    source = media["source"]["source"]

    if (media["type"] != "photo" and media["type"] != "video") or not media['canView']:
        return

    # find extension
    ext = re.findall('\.\w+\?', source)
    if len(ext) == 0:
        return
    ext = ext[0][:-1]

    if is_archived:
        path = "/archived/" + media["type"] + "s/" + id + ext
    else:
        path = "/" + media["type"] + "s/" + id + ext

    if f"{id}{ext}" not in EXIST_POST:
        # print(path)
        global new_files
        new_files += 1

        global tasks
        if len(tasks) == DOWNLOAD_LIMIT:
            asyncio.run(async_download(tasks.copy()))
            tasks = []
        else:
            tasks.append(async_download_file(source, path))


async def async_download(lst: list):
    await asyncio.gather(*lst)


async def async_download_file(source: str, path: str):
    with open("profiles/" + PROFILE + path, 'wb') as f:
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream('GET', source) as r:
                async for chunk in r.aiter_bytes():
                    f.write(chunk)

# helper to generally download files


def download_file(source: str, path: str) -> None:
    r = requests.get(source, stream=True)
    with open("profiles/" + PROFILE + path, 'wb') as f:
        r.raw.decode_content = True
        shutil.copyfileobj(r.raw, f)


def get_id_from_path(path: str) -> str:
    last_index = path.rfind("/")
    second_last_index = path.rfind("/", 0, last_index - 1)
    id = path[second_last_index + 1:last_index]
    return id


def calc_process_time(starttime, arraykey: int, arraylength: int) -> tuple:
    timeelapsed = time.time() - starttime
    timeest = (timeelapsed / arraykey) * (arraylength)
    finishtime = starttime + timeest
    finishtime = dt.datetime.fromtimestamp(
        finishtime).strftime("%H:%M:%S")  # in time
    # get a nicer looking timestamp this way
    lefttime = dt.timedelta(seconds=(int(timeest - timeelapsed)))
    timeelapseddelta = dt.timedelta(seconds=(int(timeelapsed)))  # same here
    return (timeelapseddelta, lefttime, finishtime)


# iterate over posts, downloading all media
# returns the new count of downloaded posts
def download_posts(cur_count: int, posts: list[dict[str, Any]], is_archived: bool):
    for k, post in enumerate(posts, start=1):
        if "media" not in post or ("canViewMedia" in post and not post["canViewMedia"]):
            continue

        for media in post["media"]:
            if 'source' in media:
                download_media(media, is_archived)

        # adding some nice info in here for download stats
        timestats = calc_process_time(starttime, k, total_count)
        dwnld_stats = f"{cur_count}/{total_count} {round(((cur_count / total_count) * 100))}% " + \
                      "Time elapsed: %s, Estimated Time left: %s, Estimated finish time: %s" % timestats
        end = '\n' if cur_count == total_count else '\r'
        print(dwnld_stats, end=end)

        cur_count = cur_count + 1

    return cur_count


def get_all_videos(videos: list[dict[str, Any]]):
    len_vids = len(videos)
    has_more_videos = False
    if len_vids == 50:
        has_more_videos = True

    while has_more_videos:
        has_more_videos = False
        len_vids = len(videos)
        extra_video_posts = api_request("/users/" + PROFILE_ID + "/posts/videos",
                                        getdata={"limit": str(POST_LIMIT), "order": "publish_date_desc",
                                                 "beforePublishTime": videos[len_vids - 1]["postedAtPrecise"]}
                                        )
        videos.extend(extra_video_posts)
        if len(extra_video_posts) == 50:
            has_more_videos = True

    return videos


def get_all_photos(images: list[dict[str, Any]]):
    len_imgs = len(images)
    has_more_images = False
    if len_imgs == 50:
        has_more_images = True

    while has_more_images:
        has_more_images = False
        len_imgs = len(images)
        extra_img_posts = api_request("/users/" + PROFILE_ID + "/posts/photos",
                                      getdata={"limit": str(POST_LIMIT), "order": "publish_date_desc",
                                               "beforePublishTime": images[len_imgs - 1]["postedAtPrecise"]}
                                      )
        images.extend(extra_img_posts)
        if len(extra_img_posts) == 50:
            has_more_images = True

    return images


if __name__ == "__main__":

    print("\n~~~~~~~~~~~~~~~~~~~~~~~~~~~~")
    print("~ I AM THE GREAT KORNHOLIO ~")
    print("~  ARE U THREATENING ME??  ~")
    print("~                          ~")
    print("~    COOMERS GUNNA COOM    ~")
    print("~    HACKERS GUNNA HACK    ~")
    print("~~~~~~~~~~~~~~~~~~~~~~~~~~~~\n")

    # Gather inputs
    if len(sys.argv) != 2:
        ARG1 = ""
    else:
        ARG1 = sys.argv[1]

    # Get the rules for the signed headers dynamically, as they may be fluid
    dynamic_rules = requests.get(
        'https://raw.githubusercontent.com/DATAHOARDERS/dynamic-rules/main/onlyfans.json',
        headers={
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/102.0.0.0 Safari/537.36",
        }
    ).json()
    # Create Header
    API_HEADER = create_auth()

    # Select sub
    sub_dict: dict[int | str, str] = {}
    SELECTED_MODELS = select_sub()

    # start process
    for M in SELECTED_MODELS:
        PROFILE = sub_dict[int(M)]
        PROFILE_INFO = get_user_info(PROFILE)
        PROFILE_ID = str(PROFILE_INFO["id"])

        print("\nonlyfans-dl is downloading content to profiles/" + PROFILE + "!\n")

        if os.path.isdir("profiles/" + PROFILE):
            print("\nThe folder profiles/" + PROFILE + " exists.")
            print("Media already present will not be re-downloaded.")

        assure_dir("profiles")
        assure_dir("profiles/" + PROFILE)
        assure_dir("profiles/" + PROFILE + "/avatar")
        assure_dir("profiles/" + PROFILE + "/header")
        assure_dir("profiles/" + PROFILE + "/photos")
        assure_dir("profiles/" + PROFILE + "/videos")
        assure_dir("profiles/" + PROFILE + "/archived")
        assure_dir("profiles/" + PROFILE + "/archived/photos")
        assure_dir("profiles/" + PROFILE + "/archived/videos")

        # first save profile info
        print("Saving profile info...")

        sinf = {
            "id": PROFILE_INFO["id"],
            "name": PROFILE_INFO["name"],
            "username": PROFILE_INFO["username"],
            "about": PROFILE_INFO["rawAbout"],
            "joinDate": PROFILE_INFO["joinDate"],
            "website": PROFILE_INFO["website"],
            "wishlist": PROFILE_INFO["wishlist"],
            "location": PROFILE_INFO["location"],
            "lastSeen": PROFILE_INFO["lastSeen"]
        }

        with open("profiles/" + PROFILE + "/info.json", 'w') as infojson:
            json.dump(sinf, infojson)

        download_public_files()

        # get all user posts
        print("Finding photos...", end=' ', flush=True)
        photos = api_request("/users/" + PROFILE_ID +
                             "/posts/photos", getdata={"limit": str(POST_LIMIT)})
        photo_posts = get_all_photos(photos)
        print("Found " + str(len(photo_posts)) + " photos.")
        print("Finding videos...", end=' ', flush=True)
        videos = api_request("/users/" + PROFILE_ID +
                             "/posts/videos", getdata={"limit": str(POST_LIMIT)})
        video_posts = get_all_videos(videos)
        print("Found " + str(len(video_posts)) + " videos.")
        print("Finding archived content...", end=' ', flush=True)
        archived_posts = api_request(
            "/users/" + PROFILE_ID + "/posts/archived", getdata={"limit": str(POST_LIMIT)})
        print("Found " + str(len(archived_posts)) + " archived posts.")
        postcount = len(photo_posts) + len(video_posts)
        archived_postcount = len(archived_posts)
        if postcount + archived_postcount == 0:
            print("ERROR: 0 posts found.")
            exit()

        total_count = postcount + archived_postcount

        print("Found " + str(total_count) + " posts. Downloading media...")

        photos_path = pathlib.Path("profiles/" + PROFILE + "/photos")

        # global EXIST_POST
        for file in photos_path.iterdir():
            EXIST_POST.add(file.name)
        video_path = pathlib.Path("profiles/" + PROFILE + "/videos")
        for file in video_path.iterdir():
            EXIST_POST.add(file.name)

        # get start time for estimation purposes
        starttime = time.time()

        cur_count = download_posts(1, photo_posts, False)
        cur_count = download_posts(cur_count, video_posts, False)
        download_posts(cur_count, archived_posts, True)
        time.sleep(5)

        print("Downloaded " + str(new_files) + " new files.")
