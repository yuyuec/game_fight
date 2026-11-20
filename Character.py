import RM
import pygame
import sys

class Character:
    #人物类，父类成员函数（跑跳打、血量）
    def __init__(self, walk1, walk2, junp1, junp2, fightr1, fightr2, fightl1, fightl2, fightd1, fightd2, stand1, stand2):
        self.walk1 = walk1
        self.walk2 = walk2
        self.junp1 = junp1
        self.junp2 = junp2
        self.fightr1 = fightr1
        self.fightr2 = fightr2
        self.fightl1 = fightl1
        self.fightl2 = fightl2
        self.fightd1 = fightd1
        self.fightd2 = fightd2
        self.stand1 = stand1
        self.stand2 = stand2

    def walk(self, w, h, keys):
        walk1_img = pygame.image.load(self.walk1).convert_alpha()
        walk2_img = pygame.image.load(self.walk2).convert_alpha()
        clock = pygame.time.Clock()
        player_rect = stand_img.get_rect()
        if keys[pygame.K_LEFT]:
            player_rect.x -= 5

        player_rect.center = (w // 2, h // 2)

