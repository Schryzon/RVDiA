import math

import discord
from discord.ext import commands
from discord.ui import View, Button, button


class PagedSelect(discord.ui.Select):
    def __init__(self, view, options, placeholder: str, custom_id: str) -> None:
        self.view = view
        super().__init__(
            custom_id=custom_id,
            placeholder=placeholder,
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        await self.view.handle_selection(interaction, self.values[0])


class PagedSelectionView(View):
    def __init__(
        self,
        owner_id: int,
        items: list,
        lang: str = "en",
        timeout: int | float = 30,
        timeout_per_page: int | float = 10,
        page_size: int = 25,
        select_custom_id: str = "paged_select"
    ) -> None:
        self.owner_id = owner_id
        self.items = list(items) if items else []
        self.lang = lang
        self.page_size = page_size
        self.select_custom_id = select_custom_id
        self.current_page = 0
        self.select = None
        self.timeout_base = timeout
        self.timeout_per_page = timeout_per_page
        scaled_timeout = timeout + max(0, self.max_pages - 1) * timeout_per_page
        super().__init__(timeout=scaled_timeout)
        self.refresh_page()

    @property
    def max_pages(self) -> int:
        return max(1, math.ceil(len(self.items) / self.page_size))

    def get_page_items(self) -> list:
        start = self.current_page * self.page_size
        end = start + self.page_size
        return self.items[start:end]

    def page_placeholder(self) -> str:
        return "Select an option..."

    def empty_option_label(self) -> str:
        return "Nothing here"

    def empty_option_description(self) -> str:
        return "There are no valid entries to show."

    def build_options(self, page_items: list) -> list:
        raise NotImplementedError

    async def handle_selection(self, interaction: discord.Interaction, value: str):
        raise NotImplementedError

    def owner_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.owner_id

    def not_owner_message(self) -> str:
        return "Bukan menumu." if self.lang == "id" else "Not your menu."

    def _selection_options(self) -> list:
        options = self.build_options(self.get_page_items())
        if not options:
            options = [
                discord.SelectOption(
                    label=self.empty_option_label(),
                    value="none",
                    description=self.empty_option_description()
                )
            ]
        return options

    def refresh_page(self) -> None:
        self.clear_items()
        placeholder = self.page_placeholder()
        self.select = PagedSelect(self, self._selection_options(), placeholder, self.select_custom_id)
        self.add_item(self.select)

        if self.max_pages > 1:
            self.add_item(self.prev_page)
            self.add_item(self.next_page)

    async def on_timeout(self) -> None:
        for child in self.children:
            child.disabled = True
        if hasattr(self, "message"):
            await self.message.edit(view=self)

    @button(label='◀', style=discord.ButtonStyle.blurple)
    async def prev_page(self, interaction: discord.Interaction, button: Button):
        if not self.owner_check(interaction):
            return await interaction.response.send_message(self.not_owner_message(), ephemeral=True)

        self.current_page = (self.current_page - 1) % self.max_pages
        self.refresh_page()
        await interaction.response.edit_message(view=self)

    @button(label='▶', style=discord.ButtonStyle.blurple)
    async def next_page(self, interaction: discord.Interaction, button: Button):
        if not self.owner_check(interaction):
            return await interaction.response.send_message(self.not_owner_message(), ephemeral=True)

        self.current_page = (self.current_page + 1) % self.max_pages
        self.refresh_page()
        await interaction.response.edit_message(view=self)
