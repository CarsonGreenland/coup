#!/usr/bin/env python3
"""
Coup - A card game of bluffing and deduction
CLI implementation for 1 human vs 2-3 AI opponents
"""

from enum import Enum
from random import shuffle, choice, randint, random
from typing import List, Optional, Dict, Tuple
import sys

# =============================================================================
# CONSTANTS AND ENUMS
# =============================================================================

class Card(Enum):
    DUKE = "Duke"
    ASSASSIN = "Assassin"
    CAPTAIN = "Captain"
    AMBASSADOR = "Ambassador"
    CONTESSA = "Contessa"

class Action(Enum):
    INCOME = "Income"
    FOREIGN_AID = "Foreign Aid"
    COUP = "Coup"
    TAX = "Tax"  # Duke
    ASSASSINATE = "Assassinate"  # Assassin
    STEAL = "Steal"  # Captain
    EXCHANGE = "Exchange"  # Ambassador

# Action properties: (cost, challengeable, blockable_by)
ACTION_PROPS = {
    Action.INCOME: (0, False, []),
    Action.FOREIGN_AID: (0, False, [Card.DUKE]),
    Action.COUP: (7, False, []),
    Action.TAX: (0, True, []),
    Action.ASSASSINATE: (3, True, [Card.CONTESSA]),
    Action.STEAL: (0, True, [Card.CAPTAIN, Card.AMBASSADOR]),
    Action.EXCHANGE: (0, True, []),
}

# Which card enables which action
CARD_ACTIONS = {
    Card.DUKE: Action.TAX,
    Card.ASSASSIN: Action.ASSASSINATE,
    Card.CAPTAIN: Action.STEAL,
    Card.AMBASSADOR: Action.EXCHANGE,
}

# ANSI color codes
class Colors:
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    RESET = '\033[0m'
    
    @classmethod
    def supports_color(cls):
        """Check if terminal supports colors"""
        try:
            import os
            return os.isatty(sys.stdout.fileno())
        except:
            return False

def color(text: str, color_code: str) -> str:
    """Apply color if supported"""
    if Colors.supports_color():
        return f"{color_code}{text}{Colors.RESET}"
    return text

# =============================================================================
# PLAYER CLASSES
# =============================================================================

class Player:
    """Base player class"""
    
    def __init__(self, name: str):
        self.name = name
        self.coins = 2
        self.cards: List[Card] = []  # Face-down influence
        self.revealed: List[Card] = []  # Face-up (lost influence)
        self.is_human = False
    
    @property
    def influence(self) -> int:
        """Number of active (face-down) cards"""
        return len(self.cards)
    
    @property
    def eliminated(self) -> bool:
        return self.influence == 0
    
    def add_card(self, card: Card):
        """Receive a card (face-down)"""
        self.cards.append(card)
    
    def lose_influence(self, card_index: int) -> Card:
        """Flip a card face-up (lose influence)"""
        card = self.cards.pop(card_index)
        self.revealed.append(card)
        return card
    
    def has_card(self, card: Card) -> bool:
        """Check if player has this card (for honest claims)"""
        return card in self.cards
    
    def replace_card(self, old_card: Card, new_card: Card):
        """Replace a card after successful challenge proof"""
        idx = self.cards.index(old_card)
        self.cards[idx] = new_card
    
    def __repr__(self):
        return f"{self.name} ({self.coins} coins, {self.influence} influence)"


# ── Personality presets ──────────────────────────────────────────────────────
PRESETS = {
    "The Gambler":    dict(bluff_rate=0.80, challenge_threshold=0.20, aggression=0.9, block_rate=0.3, consistency=0.60, skill=0.60),
    "The Accountant": dict(bluff_rate=0.10, challenge_threshold=0.80, aggression=0.2, block_rate=0.7, consistency=0.90, skill=0.90),
    "The Grudge":     dict(bluff_rate=0.40, challenge_threshold=0.50, aggression=0.7, block_rate=0.5, consistency=0.70, skill=0.70),
    "The Ghost":      dict(bluff_rate=0.05, challenge_threshold=0.90, aggression=0.3, block_rate=0.2, consistency=0.95, skill=0.95),
}

class AIPlayer(Player):
    """AI opponent with decision-making logic"""
    
    AI_NAMES = ["The Duke", "Lady Contessa", "Captain Vex", "Baron Bluff", "The Ambassador"]
    
    def __init__(self, name: str, preset_name: str = None):
        super().__init__(name)
        self.is_human = False
        if preset_name is None:
            preset_name = choice(list(PRESETS.keys()))
        self.preset_name = preset_name
        p = PRESETS[preset_name]
        self.bluff_rate          = p["bluff_rate"]
        self.challenge_threshold = p["challenge_threshold"]
        self.aggression          = p["aggression"]
        self.block_rate          = p["block_rate"]
        self.consistency         = p["consistency"]
        self.skill               = p["skill"]
        self.exposed_bluffs: set = set()
        self.last_challenged_by  = None
    
    def choose_action(self, game_state: 'GameState') -> Tuple[Action, Optional['Player']]:
        """Choose an action based on game state"""
        valid_actions = self._get_valid_actions(game_state)
        
        # Must coup if 10+ coins (always enforced)
        if self.coins >= 10:
            target = self._choose_coup_target(game_state)
            return Action.COUP, target

        # Low skill: occasionally just bumble and take Income
        if random() > self.skill:
            return choice([Action.INCOME, Action.FOREIGN_AID]), None

        # Prefer strong actions when profitable
        if self.coins >= 7 and self._should_coup(game_state):
            target = self._choose_coup_target(game_state)
            return Action.COUP, target
        
        # Consider Tax (Duke) - always good
        if self._should_claim(Card.DUKE, game_state):
            return Action.TAX, None
        
        # Consider Steal (Captain) if targets have coins
        steal_target = self._choose_steal_target(game_state)
        if steal_target:
            return Action.STEAL, steal_target
        
        # Consider Assassinate if we have 3+ coins
        if self.coins >= 3 and self._should_assassinate(game_state):
            target = self._choose_assassinate_target(game_state)
            if target:
                return Action.ASSASSINATE, target
        
        # Fallback to income or foreign aid
        if randint(0, 1) == 0:
            return Action.INCOME, None
        else:
            return Action.FOREIGN_AID, None
    
    def _get_valid_actions(self, game_state: 'GameState') -> List[Action]:
        """Get list of actions we can afford"""
        actions = [Action.INCOME, Action.FOREIGN_AID, Action.TAX, Action.STEAL, Action.EXCHANGE]
        if self.coins >= 3:
            actions.append(Action.ASSASSINATE)
        if self.coins >= 7:
            actions.append(Action.COUP)
        return actions
    
    def _should_coup(self, game_state: 'GameState') -> bool:
        """Decide if we should coup"""
        return self.coins >= 7 and randint(0, 2) == 0
    
    def _choose_coup_target(self, game_state: 'GameState'):
        """Choose who to coup — aggression + grudge"""
        targets = [p for p in game_state.active_players if p != self]
        if not targets:
            return None
        if self.last_challenged_by and self.last_challenged_by in targets and random() < 0.7:
            return self.last_challenged_by
        if random() < self.aggression:
            targets.sort(key=lambda p: -p.coins)
        else:
            targets.sort(key=lambda p: (p.influence, -p.coins))
        return targets[0]
    
    def _should_claim(self, card: Card, game_state: 'GameState') -> bool:
        """Decide if we should claim to have a card (honestly or bluff)"""
        if card in self.exposed_bluffs:
            return self.has_card(card)
        if self.has_card(card):
            return True
        if random() > self.consistency:
            return random() < 0.25  # Inconsistent — random noise
        unknown_copies = game_state.unknown_copies(card, self)
        return random() < (unknown_copies / 3.0) * self.bluff_rate
    
    def _choose_steal_target(self, game_state: 'GameState') -> Optional['Player']:
        """Choose who to steal from"""
        targets = [p for p in game_state.active_players if p != self and p.coins >= 2]
        if not targets:
            targets = [p for p in game_state.active_players if p != self and p.coins >= 1]
        if not targets:
            return None
        
        # Prefer targets with more coins
        targets.sort(key=lambda p: -p.coins)
        return targets[0]
    
    def _should_assassinate(self, game_state: 'GameState') -> bool:
        """Decide if we should assassinate"""
        return self.coins >= 3 and randint(0, 2) <= 1
    
    def _choose_assassinate_target(self, game_state: 'GameState') -> Optional['Player']:
        """Choose who to assassinate"""
        targets = [p for p in game_state.active_players if p != self]
        # Prefer targets with 1 influence (elimination)
        one_inf = [p for p in targets if p.influence == 1]
        if one_inf:
            return choice(one_inf)
        return choice(targets) if targets else None
    
    def decide_challenge(self, action: Action, claimed_card,
                         actor, game_state) -> bool:
        """Decide whether to challenge"""
        if claimed_card is None:
            return False
        if random() > self.consistency:
            return random() < 0.15
        revealed_count = sum(1 for p in game_state.active_players for c in p.revealed if c == claimed_card)
        our_count = sum(1 for c in self.cards if c == claimed_card)
        remaining = max(0, 3 - revealed_count - our_count)
        p_has = remaining / 3.0
        return random() > (p_has + self.challenge_threshold * 0.5)

    def decide_block(self, action: Action, actor, game_state) -> object:
        """Decide whether and how to block"""
        if random() > self.consistency:
            return None
        if action == Action.FOREIGN_AID:
            if self.has_card(Card.DUKE) and random() < self.block_rate:
                return Card.DUKE
            if self._should_bluff_block(Card.DUKE, game_state):
                return Card.DUKE
        elif action == Action.ASSASSINATE:
            if self.has_card(Card.CONTESSA) and random() < self.block_rate:
                return Card.CONTESSA
            if self._should_bluff_block(Card.CONTESSA, game_state):
                return Card.CONTESSA
        elif action == Action.STEAL:
            for card in [Card.CAPTAIN, Card.AMBASSADOR]:
                if self.has_card(card) and random() < self.block_rate:
                    return card
            for card in [Card.CAPTAIN, Card.AMBASSADOR]:
                if self._should_bluff_block(card, game_state):
                    return card
        return None

    def _should_bluff_block(self, card: Card, game_state: 'GameState') -> bool:
        """Decide if we should bluff a block"""
        if card in self.exposed_bluffs:
            return False
        return random() < self.bluff_rate * self.block_rate * 0.3
    
    def respond_to_challenge(self, claimed_card: Card) -> bool:
        """Handle being challenged - return True if we can prove"""
        return self.has_card(claimed_card)
    
    def choose_exchange(self, drawn_cards: List[Card], game_state: 'GameState') -> List[Card]:
        """Choose which cards to keep after Exchange"""
        # Keep the best cards (prefer Duke, Assassin, Captain)
        priority = [Card.DUKE, Card.ASSASSIN, Card.CAPTAIN, Card.AMBASSADOR, Card.CONTESSA]
        
        all_cards = self.cards + drawn_cards
        kept = []
        
        # Try to keep highest priority cards
        for card_type in priority:
            for card in all_cards:
                if card == card_type and len(kept) < 2:
                    if card not in kept:
                        kept.append(card)
        
        # Fill remaining slots
        for card in all_cards:
            if len(kept) >= 2:
                break
            if card not in kept:
                kept.append(card)
        
        return kept[:2]
    
    def choose_lose_influence(self, game_state: 'GameState') -> int:
        """Choose which card to lose when losing influence"""
        if len(self.cards) == 1:
            return 0
        
        # Prefer to keep Duke and Assassin
        priority = {Card.DUKE: 0, Card.ASSASSIN: 1, Card.CAPTAIN: 2, 
                   Card.AMBASSADOR: 3, Card.CONTESSA: 4}
        
        # Lose lowest priority card
        min_priority = 10
        lose_idx = 0
        for i, card in enumerate(self.cards):
            if priority.get(card, 5) < min_priority:
                min_priority = priority.get(card, 5)
                lose_idx = i
        
        return lose_idx


class GameState:
    """Tracks game state for AI decisions"""
    
    def __init__(self, players: List[Player], court_deck: List[Card]):
        self.players = players
        self.court_deck = court_deck
    
    @property
    def active_players(self) -> List[Player]:
        return [p for p in self.players if not p.eliminated]
    
    def unknown_copies(self, card: Card, exclude_player: Player) -> int:
        """Count how many copies of a card are unaccounted for"""
        total = 3
        # Subtract revealed cards
        for p in self.players:
            if p == exclude_player:
                continue
            total -= sum(1 for c in p.revealed if c == card)
        # Subtract our own cards if we're not excluded
        if exclude_player != self:
            pass  # Don't count our cards as unknown
        return max(0, total)


# =============================================================================
# GAME ENGINE
# =============================================================================

class GameEngine:
    """Main game state machine"""
    
    def __init__(self, num_ai: int = 2):
        self.players: List[Player] = []
        self.court_deck: List[Card] = []
        self.current_player_idx = 0
        self.game_over = False
        self.winner: Optional[Player] = None
        self.round_num = 1
        self.rounds_to_win = 1
        
        # Create deck: 3 of each card
        self._create_deck()
        
        # Create players
        self._create_players(num_ai)
        
        # Deal initial cards
        self._deal_initial_cards()
    
    def _create_deck(self):
        """Create and shuffle the court deck"""
        self.court_deck = []
        for card in Card:
            for _ in range(3):
                self.court_deck.append(card)
        shuffle(self.court_deck)
    
    def _create_players(self, num_ai: int):
        """Create human and AI players"""
        # Human player
        human = Player("You")
        human.is_human = True
        self.players.append(human)
        
        # AI players
        all_presets = list(PRESETS.keys())
        shuffle(all_presets)
        assigned = [all_presets[i % len(all_presets)] for i in range(num_ai)]
        for i in range(num_ai):
            name = AIPlayer.AI_NAMES[i] if i < len(AIPlayer.AI_NAMES) else f"AI {i+1}"
            ai = AIPlayer(name, preset_name=assigned[i])
            self.players.append(ai)
    
    def show_personality_reveal(self):
        print(color("\n--- AI Personalities (now revealed) ---", Colors.CYAN))
        for p in self.players:
            if not p.is_human and hasattr(p, 'preset_name'):
                pr = PRESETS[p.preset_name]
                print(color(f"  {p.name} was: {p.preset_name}", Colors.YELLOW))
                print(f"    bluff={pr['bluff_rate']:.2f}  challenge_thresh={pr['challenge_threshold']:.2f}  aggression={pr['aggression']:.2f}")
                print(f"    block={pr['block_rate']:.2f}  consistency={pr['consistency']:.2f}  skill={pr['skill']:.2f}")

    def reset_for_new_round(self):
        """Reset deck/cards/coins for a new round, keeping players and personalities."""
        self.game_over = False
        self.winner = None
        self.current_player_idx = 0
        self._create_deck()
        for player in self.players:
            player.coins = 2
            player.cards = []
            player.revealed = []
            if hasattr(player, 'exposed_bluffs'):
                player.exposed_bluffs = set()
            if hasattr(player, 'last_challenged_by'):
                player.last_challenged_by = None
        self._deal_initial_cards()

    def _deal_initial_cards(self):
        """Deal 2 cards to each player"""
        for player in self.players:
            for _ in range(2):
                player.add_card(self.court_deck.pop())
    
    def _draw_card(self) -> Card:
        """Draw a card from the deck"""
        if not self.court_deck:
            return None
        return self.court_deck.pop()
    
    def _return_card(self, card: Card):
        """Return a card to the deck and shuffle"""
        self.court_deck.append(card)
        shuffle(self.court_deck)
    
    def _get_game_state(self) -> GameState:
        """Get current game state for AI decisions"""
        return GameState(self.players, self.court_deck)
    
    @property
    def current_player(self) -> Player:
        return self.players[self.current_player_idx]
    
    @property
    def active_players(self) -> List[Player]:
        return [p for p in self.players if not p.eliminated]
    
    def next_turn(self):
        """Advance to next active player"""
        while True:
            self.current_player_idx = (self.current_player_idx + 1) % len(self.players)
            if not self.current_player.eliminated:
                break
    
    def check_game_over(self) -> bool:
        """Check if game is over"""
        active = self.active_players
        if len(active) == 1:
            self.game_over = True
            self.winner = active[0]
            return True
        return False
    
    def get_action_card(self, action: Action) -> Optional[Card]:
        """Get the card required for a character action"""
        for card, card_action in CARD_ACTIONS.items():
            if card_action == action:
                return card
        return None
    
    def get_block_cards(self, action: Action) -> List[Card]:
        """Get cards that can block an action"""
        return ACTION_PROPS.get(action, (0, False, []))[2]
    
    def display_game_state(self):
        """Show current game state"""
        print("\n" + "=" * 60)
        round_label = f"COUP — Round {self.round_num}" + (f" of {self.rounds_to_win}" if self.rounds_to_win > 1 else "")
        print(color(round_label, Colors.BOLD + Colors.CYAN))
        print("=" * 60)
        
        for player in self.players:
            if player.eliminated:
                status = color("ELIMINATED", Colors.RED + Colors.DIM)
            else:
                status = f"{player.coins} coins, {player.influence} influence"
            
            print(f"\n{color(player.name, Colors.BOLD)}: {status}")
            
            # Show revealed cards
            if player.revealed:
                revealed_str = ", ".join(c.value for c in player.revealed)
                print(f"  Revealed: {color(revealed_str, Colors.DIM)}")
            
            # Show human's own cards
            if player.is_human and player.cards:
                cards_str = ", ".join(color(c.value, Colors.GREEN) for c in player.cards)
                print(f"  Your cards: {cards_str}")
        
        print("\n" + "-" * 60)
    
    def announce(self, message: str, color_code: str = Colors.WHITE):
        """Print an announcement"""
        print(color(message, color_code))
    
    def human_choose_action(self) -> Tuple[Action, Optional[Player]]:
        """Get action choice from human player"""
        human = self.current_player
        
        # Check for forced coup
        if human.coins >= 10:
            print(color("\nYou have 10+ coins - you MUST Coup!", Colors.YELLOW))
            target = self._human_choose_target()
            return Action.COUP, target
        
        # Show available actions
        print(color("\nAvailable actions:", Colors.CYAN))
        print("  1. Income (+1 coin)")
        print("  2. Foreign Aid (+2 coins, blockable by Duke)")
        print("  3. Tax [Duke] (+3 coins)")
        print("  4. Steal [Captain] (take 2 coins from target)")
        print("  5. Exchange [Ambassador] (swap cards with deck)")
        
        if human.coins >= 3:
            print(f"  6. Assassinate [Assassin] (-3 coins, target loses influence)")
        if human.coins >= 7:
            print(f"  7. Coup (-7 coins, target loses influence)")
        
        while True:
            try:
                choice = input(color("\nChoose action (1-7): ", Colors.YELLOW)).strip()
                choice_idx = int(choice) - 1
                
                actions = [Action.INCOME, Action.FOREIGN_AID, Action.TAX, 
                          Action.STEAL, Action.EXCHANGE]
                if human.coins >= 3:
                    actions.append(Action.ASSASSINATE)
                if human.coins >= 7:
                    actions.append(Action.COUP)
                
                if 0 <= choice_idx < len(actions):
                    action = actions[choice_idx]
                    break
                print(color("Invalid choice. Try again.", Colors.RED))
            except ValueError:
                print(color("Please enter a number.", Colors.RED))
        
        # Get target if needed
        target = None
        if action in [Action.COUP, Action.ASSASSINATE, Action.STEAL]:
            target = self._human_choose_target()
        
        return action, target
    
    def _human_choose_target(self) -> Player:
        """Get target choice from human"""
        targets = [p for p in self.active_players if p != self.current_player]
        
        print(color("\nChoose target:", Colors.CYAN))
        for i, target in enumerate(targets):
            print(f"  {i+1}. {target.name} ({target.coins} coins, {target.influence} influence)")
        
        while True:
            try:
                choice = input(color("Target: ", Colors.YELLOW)).strip()
                choice_idx = int(choice) - 1
                if 0 <= choice_idx < len(targets):
                    return targets[choice_idx]
                print(color("Invalid choice.", Colors.RED))
            except ValueError:
                print(color("Please enter a number.", Colors.RED))
    
    def human_choose_lose_influence(self) -> int:
        """Human chooses which card to lose"""
        human = self.players[0]  # Assuming human is first
        print(color("\nYou must lose an influence!", Colors.RED))
        
        if len(human.cards) == 1:
            print(f"  → {human.cards[0].value} is revealed automatically.")
            return 0
        
        print("Which card will you sacrifice?")
        for i, card in enumerate(human.cards):
            print(f"  {i+1}. {card.value}")
        
        while True:
            try:
                choice = input(color("Choice: ", Colors.YELLOW)).strip()
                choice_idx = int(choice) - 1
                if 0 <= choice_idx < len(human.cards):
                    return choice_idx
                print(color("Invalid choice.", Colors.RED))
            except ValueError:
                print(color("Please enter a number.", Colors.RED))
    
    def process_turn(self):
        """Process one complete turn"""
        actor = self.current_player
        game_state = self._get_game_state()
        
        # Get action
        if actor.is_human:
            action, target = self.human_choose_action()
        else:
            action, target = actor.choose_action(game_state)
            print(f"\n{actor.name} chooses: {action.value}" + 
                  (f" targeting {target.name}" if target else ""))
        
        # Deduct cost
        cost = ACTION_PROPS[action][0]
        if cost > 0:
            actor.coins -= cost
        
        # Get claimed card (if any)
        claimed_card = self.get_action_card(action)
        is_challengeable = ACTION_PROPS[action][1]
        block_cards = self.get_block_cards(action)
        
        # Handle challenges and blocks
        if is_challengeable or block_cards:
            challenge_result = self._process_challenges(action, claimed_card, actor, target)
            
            if challenge_result == "challenged_and_failed":
                # Action failed, refund coins if applicable
                if action == Action.ASSASSINATE:
                    actor.coins += cost
                return  # Turn ends
            
            # Check for blocks regardless of whether a challenge was attempted.
            # A failed challenge (actor proved their card) does not prevent blocking.
            if block_cards:
                block_result = self._process_blocks(action, actor, target, block_cards)
                
                if block_result == "blocked":
                    return  # Turn ends
                elif block_result == "challenged_block":
                    # Block was successfully challenged, action proceeds
                    pass
        
        # Execute action
        self._execute_action(action, actor, target)
    
    def _process_challenges(self, action: Action, claimed_card: Optional[Card],
                           actor: Player, target: Player) -> str:
        """Process challenges to an action. Returns result."""
        if not claimed_card:
            return "no_challenge_possible"
        
        game_state = self._get_game_state()
        
        # Poll each other player for challenge
        for player in self.active_players:
            if player == actor:
                continue
            
            should_challenge = False
            
            if player.is_human:
                # Ask human
                print(color(f"\n{actor.name} claims {claimed_card.value} for {action.value}.", Colors.CYAN))
                response = input(color(f"Challenge? (y/n): ", Colors.YELLOW)).strip().lower()
                should_challenge = response == 'y'
            else:
                should_challenge = player.decide_challenge(action, claimed_card, actor, game_state)
            
            if should_challenge:
                print(color(f"\n{player.name} challenges {actor.name}!", Colors.MAGENTA))
                
                # Can actor prove it?
                if actor.has_card(claimed_card):
                    # Actor proves it!
                    print(color(f"{actor.name} reveals {claimed_card.value} - challenge FAILED!", Colors.GREEN))
                    
                    # Challenger loses influence
                    self._lose_influence(player)
                    
                    # Actor returns proved card to deck and draws a replacement
                    old_card = claimed_card
                    new_card = self._draw_card()
                    actor.replace_card(old_card, new_card)
                    self._return_card(old_card)
                    actor_label = "You return" if actor.is_human else f"{actor.name} returns"
                    print(color(f"{actor_label} {old_card.value} to the deck and draws a replacement.", Colors.CYAN))
                    
                    return "challenged_and_succeeded"
                else:
                    # Actor was bluffing!
                    print(color(f"{actor.name} cannot prove {claimed_card.value} - challenge SUCCEEDED!", Colors.RED))
                    
                    # Record the exposed bluff so AI won't repeat it
                    if hasattr(actor, 'exposed_bluffs'):
                        actor.exposed_bluffs.add(claimed_card)
                    # Grudge: remember who caught us
                    if hasattr(actor, 'last_challenged_by'):
                        actor.last_challenged_by = player
                    
                    # Actor loses influence; action fails; coins refunded in process_turn
                    self._lose_influence(actor)
                    
                    return "challenged_and_failed"
        
        return "no_challenge"
    
    def _process_blocks(self, action: Action, actor: Player, target: Player,
                       block_cards: List[Card]) -> str:
        """Process blocks to an action. Returns result."""
        if not block_cards:
            return "no_block_possible"
        
        game_state = self._get_game_state()
        
        # For Foreign Aid, any player can block (claiming Duke).
        # For Steal/Assassinate, only the target can block.
        potential_blockers = self.active_players if action == Action.FOREIGN_AID else ([target] if target and not target.eliminated else [])
        
        blocking_card = None
        blocker = None
        
        for candidate in potential_blockers:
            if candidate == actor:
                continue
            
            if candidate.is_human:
                card_names = " or ".join(c.value for c in block_cards)
                if action == Action.FOREIGN_AID:
                    print(color(f"\n{actor.name} attempts Foreign Aid.", Colors.CYAN))
                else:
                    print(color(f"\n{actor.name} attempts {action.value} against you!", Colors.CYAN))
                print(f"You can block with {card_names}.")
                response = input(color("Block? (y/n): ", Colors.YELLOW)).strip().lower()
                if response == 'y':
                    if len(block_cards) == 1:
                        blocking_card = block_cards[0]
                    else:
                        print("Which card do you claim?")
                        for i, card in enumerate(block_cards):
                            print(f"  {i+1}. {card.value}")
                        while True:
                            try:
                                choice = input(color("Choice: ", Colors.YELLOW)).strip()
                                choice_idx = int(choice) - 1
                                if 0 <= choice_idx < len(block_cards):
                                    blocking_card = block_cards[choice_idx]
                                    break
                            except ValueError:
                                pass
                    if blocking_card:
                        blocker = candidate
                        break
            else:
                bc = candidate.decide_block(action, actor, game_state)
                if bc:
                    blocking_card = bc
                    blocker = candidate
                    break
        
        if blocking_card and blocker:
            print(color(f"\n{blocker.name} blocks with {blocking_card.value}!", Colors.YELLOW))
            
            # Block can be challenged
            for player in self.active_players:
                if player == blocker:
                    continue
                
                should_challenge = False
                
                if player.is_human:
                    response = input(color(f"Challenge {blocker.name}'s block? (y/n): ", 
                                          Colors.YELLOW)).strip().lower()
                    should_challenge = response == 'y'
                else:
                    should_challenge = player.decide_challenge(action, blocking_card, blocker, game_state)
                
                if should_challenge:
                    print(color(f"{player.name} challenges the block!", Colors.MAGENTA))
                    
                    if blocker.has_card(blocking_card):
                        # Block succeeds, challenger loses influence
                        print(color(f"{blocker.name} proves {blocking_card.value} - block stands!", Colors.GREEN))
                        self._lose_influence(player)
                        
                        # Replace card
                        new_card = self._draw_card()
                        blocker.replace_card(blocking_card, new_card)
                        self._return_card(blocking_card)
                        blocker_label = "You return" if blocker.is_human else f"{blocker.name} returns"
                        print(color(f"{blocker_label} {blocking_card.value} to the deck and draws a replacement.", Colors.CYAN))
                        
                        return "blocked"
                    else:
                        # Block fails, blocker loses influence
                        print(color(f"{blocker.name} cannot prove {blocking_card.value}!", Colors.RED))
                        if hasattr(blocker, 'exposed_bluffs'):
                            blocker.exposed_bluffs.add(blocking_card)
                        self._lose_influence(blocker)
                        return "challenged_block"
            
            # No challenge to block
            return "blocked"
        
        return "no_block"
    
    def _execute_action(self, action: Action, actor: Player, target: Optional[Player]):
        """Execute the final action"""
        if action == Action.INCOME:
            actor.coins += 1
            self.announce(f"{actor.name} takes Income (+1 coin)", Colors.GREEN)
        
        elif action == Action.FOREIGN_AID:
            actor.coins += 2
            self.announce(f"{actor.name} takes Foreign Aid (+2 coins)", Colors.GREEN)
        
        elif action == Action.TAX:
            actor.coins += 3
            self.announce(f"{actor.name} collects Tax (+3 coins)", Colors.GREEN)
        
        elif action == Action.COUP:
            self.announce(f"{actor.name} COUPS {target.name}!", Colors.RED)
            self._lose_influence(target)
        
        elif action == Action.ASSASSINATE:
            self.announce(f"{actor.name} assassinates {target.name}!", Colors.RED)
            self._lose_influence(target)
        
        elif action == Action.STEAL:
            stolen = min(2, target.coins)
            target.coins -= stolen
            actor.coins += stolen
            self.announce(f"{actor.name} steals {stolen} coins from {target.name}!", Colors.YELLOW)
        
        elif action == Action.EXCHANGE:
            self._handle_exchange(actor)
    
    def _handle_exchange(self, player: Player):
        """Handle Ambassador exchange action"""
        # Draw 2 cards
        drawn = [self._draw_card(), self._draw_card()]
        
        if player.is_human:
            print(color("\nYou draw 2 cards from the Court deck:", Colors.CYAN))
            all_cards = player.cards + drawn
            for i, card in enumerate(all_cards):
                print(f"  {i+1}. {card.value}")
            
            print("Choose 2 cards to keep:")
            kept_indices = []
            while len(kept_indices) < 2:
                try:
                    choice = input(color(f"Card {len(kept_indices)+1}: ", Colors.YELLOW)).strip()
                    choice_idx = int(choice) - 1
                    if 0 <= choice_idx < len(all_cards) and choice_idx not in kept_indices:
                        kept_indices.append(choice_idx)
                    else:
                        print(color("Invalid or duplicate choice.", Colors.RED))
                except ValueError:
                    print(color("Please enter a number.", Colors.RED))
            
            # Return unchosen cards to deck
            player.cards = [all_cards[i] for i in kept_indices]
            for i, card in enumerate(all_cards):
                if i not in kept_indices:
                    self._return_card(card)
        else:
            # AI chooses
            kept = player.choose_exchange(drawn, self._get_game_state())
            returned = [c for c in player.cards + drawn if c not in kept or 
                       (player.cards + drawn).count(c) > kept.count(c)]
            player.cards = kept
            for card in returned[:2]:  # Return 2 cards
                self._return_card(card)
        
        self.announce(f"{player.name} exchanges cards with the Court deck", Colors.CYAN)
        # Clear exposed bluffs — new hand may include previously-bluffed cards
        if hasattr(player, 'exposed_bluffs'):
            player.exposed_bluffs.clear()
    
    def _lose_influence(self, player: Player):
        """Player loses one influence"""
        if player.influence == 0:
            return
        
        if player.is_human:
            card_idx = self.human_choose_lose_influence()
        else:
            card_idx = player.choose_lose_influence(self._get_game_state())
        
        card = player.lose_influence(card_idx)
        self.announce(f"{player.name} loses {card.value}!", Colors.RED)
        
        if player.eliminated:
            self.announce(f"{player.name} is ELIMINATED!", Colors.RED + Colors.BOLD)
    
    def run(self):
        """Main game loop"""
        while not self.game_over:
            self.display_game_state()
            
            # Skip eliminated players
            if self.current_player.eliminated:
                self.next_turn()
                continue
            
            try:
                self.process_turn()
            except KeyboardInterrupt:
                print(color("\n\nGame aborted.", Colors.YELLOW))
                return
            
            if self.check_game_over():
                break
            
            self.next_turn()
        
        # Reveal all hidden cards before announcing winner
        print(color("\n" + "=" * 60, Colors.CYAN))
        print(color("FINAL REVEAL — All hidden cards exposed:", Colors.BOLD + Colors.CYAN))
        for player in self.players:
            hidden = player.cards  # still face-down cards
            if hidden:
                card_str = ", ".join(c.value for c in hidden)
                label = "You" if player.is_human else player.name
                status = "winner" if player == self.winner else "eliminated"
                print(color(f"  {label} [{status}]: was holding {card_str}", Colors.YELLOW))
        print(color("=" * 60, Colors.CYAN))

        # Announce winner
        self.display_game_state()
        winner_name = "You" if self.winner.is_human else self.winner.name
        win_verb = "WIN" if self.winner.is_human else "WINS"
        print(color(f"\n🏆 {winner_name} {win_verb}! 🏆", Colors.GREEN + Colors.BOLD))

        # (Personality reveal shown at match end only)


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

def main():
    """Main entry point for the game"""
    print(color("\n" + "=" * 60, Colors.CYAN))
    print(color("COUP - A Game of Bluff and Deduction", Colors.BOLD + Colors.CYAN))
    print(color("=" * 60, Colors.CYAN))
    print("\nIn the world of Coup, you fight for control.")
    print("Bluff, deceive, and eliminate your opponents!")
    print("\nEach player starts with 2 coins and 2 hidden influence cards.")
    print("The last player standing wins!")
    
    # Get number of AI opponents
    print("\n" + color("How many AI opponents? (2-5): ", Colors.YELLOW))
    
    while True:
        try:
            num_ai = input().strip()
            num_ai = int(num_ai)
            if 2 <= num_ai <= 5:
                break
            print(color("Please enter 2-5.", Colors.RED))
        except ValueError:
            print(color("Please enter a number.", Colors.RED))
    
    # Quick rules
    print("\n" + color("Quick Reference:", Colors.BOLD))
    print("  Actions: Income(+1), Foreign Aid(+2), Tax/Duke(+3)")
    print("  Steal/Captain(take 2), Assassinate(-3 coins), Coup(-7 coins)")
    print("  Exchange/Ambassador(swap cards)")
    print("\n  Challenge: Call someone's bluff - loser loses an influence")
    print("  Block: Stop Foreign Aid (Duke), Steal (Capt/Amb), Assassinate (Contessa)")
    print(color("\n" + "=" * 60 + "\n", Colors.CYAN))
    
    # Ask rounds to win
    print(color("\nRounds needed to win the match? (1-5): ", Colors.YELLOW))
    while True:
        try:
            rounds_to_win = int(input().strip())
            if 1 <= rounds_to_win <= 5:
                break
            print(color("Please enter 1-5.", Colors.RED))
        except ValueError:
            print(color("Please enter a number.", Colors.RED))

    # Create game (personalities assigned once for the whole match)
    game = GameEngine(num_ai)
    game.rounds_to_win = rounds_to_win
    wins = {p.name: 0 for p in game.players}
    round_num = 0

    while True:
        round_num += 1
        if rounds_to_win > 1:
            print(color(f"\n{'=' * 60}", Colors.CYAN))
            print(color(f"  ROUND {round_num}", Colors.BOLD + Colors.CYAN))
            # Show match standings
            standing_parts = [f"{name}: {w} win{'s' if w != 1 else ''}" for name, w in wins.items()]
            print(color(f"  Standings: {', '.join(standing_parts)}", Colors.CYAN))
            print(color(f"  First to {rounds_to_win} wins the match", Colors.CYAN))
            print(color(f"{'=' * 60}", Colors.CYAN))

        game.run()

        # Record win
        if game.winner:
            wins[game.winner.name] += 1
            match_winner = next((name for name, w in wins.items() if w >= rounds_to_win), None)
            if match_winner:
                print(color(f"\n{'=' * 60}", Colors.GREEN))
                print(color(f"  🏆 {match_winner} WINS THE MATCH! 🏆", Colors.BOLD + Colors.GREEN))
                print(color(f"{'=' * 60}", Colors.GREEN))
                game.show_personality_reveal()
                break

        # Show standings between rounds
        if rounds_to_win > 1:
            print(color("\nMatch standings:", Colors.CYAN))
            for name, w in wins.items():
                bar = "█" * w + "░" * (rounds_to_win - w)
                print(f"  {name}: {bar} ({w}/{rounds_to_win})")

        print(color("\nPlay next round? (y/n): ", Colors.YELLOW))
        response = input().strip().lower()
        if response != 'y':
            game.show_personality_reveal()
            print(color("\nThanks for playing Coup!", Colors.GREEN))
            break

        print("\n" + color("=" * 60, Colors.CYAN))
        print(color(f"ROUND {round_num + 1} — Same personalities, new deal", Colors.BOLD + Colors.CYAN))
        print(color("=" * 60, Colors.CYAN))
        game.reset_for_new_round()
        game.round_num = round_num + 1
        game.rounds_to_win = rounds_to_win


if __name__ == "__main__":
    main()
