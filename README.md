> [!IMPORTANT]
> [`** REQUIRES PYTHON 3.12.7+ **`](https://www.python.org/downloads/release/python-3127/)
> </br>`pip install -U requirements.txt`

</br>
</br>

> [!CAUTION]
> ### **Policy for upstream use**
>
> </br>
>
> #1) Assets that would result in your or others delistment will be considered forbidden.
>
> </br>
>
> #2) No cheats, such as grenade trail PK3s, or invisible scopes are permitted.
>
> </br>
>
> #3) If you are modifying existing assets, you must include this in your repository description.
>
> </br>
>
> #4) Your release tags on your repository must follow [semantic versioning.](https://chatgpt.com/share/688f11fa-27cc-8012-8659-74440a468533)
>
> </br>
>
> #5) Ensure you have no stolen assets and provide an index of special thanks & credit attribution.
>
> </br>
>
> #6) All assets must be MBII related upon inspection.

</br>
</br>

> [!NOTE]
> ### **Adding your own MBII project**
>
> </br>
>
> #1) Create a github repository.
>
> </br>
>
> #2) On your created repository, place and push your custom assets.
>
> </br>
>
> #3) Go to the releases tab, create a release with [semantic versioning](https://chatgpt.com/share/688f11fa-27cc-8012-8659-74440a468533) and the release package as `release.zip` with your .PK3 inside.
>
> </br>
>
> #4) Create a fork of this repository.
>
> </br>
>
> #5) Edit `repositories.json` in the root working directory of the forked repository, fill out the following:
> ```
> "name" - following the format of your repo URL, "{USER OR ORG}/{REPO NAME}"
> "custom_name" - required, a brief name descriptor of your custom asset
> "description" - description of your custom asset, default obtained by repository
> "url" - your URL to the repository, "https://github.com/{USER OR ORG}/{REPO NAME}"
> 
> ** RESPECT INDENTATION AND PROPERLY CLOSE BRACKETS AND PROPER CHARACTER ESCAPES **
> ```
>
> </br>
>
> #6) Push and commit your changes.
>
> </br>
>
> #7) Open a pull request to the [`merge`](https://github.com/MBII-Galactic-Conquest/mbii-community-updater/tree/merge) branch of the [upstream](https://github.com/MBII-Galactic-Conquest/mbii-community-updater/) repository.
