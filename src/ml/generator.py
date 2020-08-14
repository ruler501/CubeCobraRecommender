import json
from collections import Counter
from pathlib import Path

from tensorflow.keras.utils import Sequence
from tensorflow.keras.preprocessing.sequence import skipgrams
import numpy as np
import random


class DataGenerator(Sequence):

    def __init__(
        self,
        adj_mtx,
        cubes,
        num_cards,
        batch_size=64,
        shuffle=True,
        to_fit=True,
        noise=0.2,
        noise_std=0.1,
    ):
        self.noise_std = noise_std
        self.batch_size = batch_size
        self.shuffle = shuffle
        self.to_fit = to_fit
        self.noise = noise
        # initialize inputs and outputs
        self.y_reg = adj_mtx
        self.x_reg = np.zeros_like(adj_mtx)
        np.fill_diagonal(self.x_reg, 1)
        self.x_main = cubes
        self.max_cube_size = len(cubes[0])
        # initialize other needed inputs
        self.N_cubes = len(cubes)
        self.N_cards = num_cards
        self.neg_sampler = adj_mtx.sum(0)/adj_mtx.sum()
        self.cube_includes = [[x for x in cube if x > 0] for cube in cubes]
        self.cube_includes_set = [set(includes) for includes in self.cube_includes]
        self.cube_excludes = [[x - 1 for x in range(1, self.N_cards + 1) if x not in includes_set]
                              for includes_set in self.cube_includes_set]
        del self.cube_includes_set
        self.neg_samplers = [self.neg_sampler[excludes]
                             / self.neg_sampler[excludes].sum()
                             for excludes in self.cube_excludes]
        # self.pool = Pool(30)
        self.indices = np.arange(self.N_cubes)
        self.batches = []
        self.reset_indices()

    def __len__(self):
        """
        return: number of batches per epoch
        """
        return self.N_cubes // self.batch_size

    def __getitem(self, batch_number):
        """
        Generates a data mini-batch
        param batch_number: which batch to generate
        return: X and y when fitting. X only when predicting
        """
        main_indices = self.indices[
            batch_number * self.batch_size:(batch_number + 1) * self.batch_size
        ]
        reg_indices = np.random.choice(
            np.arange(self.N_cards),
            len(main_indices),
            p=self.neg_sampler,
            replace=False,
        )

        X, y = self.generate_data(
            main_indices,
            reg_indices,
        )
        if self.to_fit:
            return [X[0], X[1]], [y[0], y[1]]
        else:
            return [X[0], X[1]]

    def __getitem__(self, batch_number):
        return self.__getitem(batch_number)
        # return self.batches[batch_number].get()

    def reset_indices(self):
        self.indices = np.arange(self.N_cubes)
        if self.shuffle:
            np.random.shuffle(self.indices)
        # print('starting to calculate batches')
        # self.batches = [self.pool.apply_async(self.__getitem, (i,))
        #                 for i in range(len(self))]
        # print('started calculating batches')

    def on_epoch_end(self):
        """
        Update indices after each epoch
        """
        self.reset_indices()

    def generate_data(self, main_indices, reg_indices):
        cubes = [self.x_main[i] for i in main_indices]
        cube_includes = [self.cube_includes[i] for i in main_indices]
        cube_excludes = [self.cube_excludes[i] for i in main_indices]
        neg_samplers = [self.neg_samplers[i] for i in main_indices]
        x_regularization = np.zeros((len(reg_indices), self.max_cube_size)).astype(int)        
        for i, x in enumerate(reg_indices):
            x_regularization[i, 0] = x
        y_regularization = self.y_reg[reg_indices]
        y_cubes = np.zeros((len(main_indices), self.N_cards))

        processed_cubes = []
        for i, cube, includes, excludes, neg_sampler \
            in zip(range(len(cubes)), cubes, cube_includes, cube_excludes, neg_samplers):
            size = len(includes)
            noise = np.clip(
                np.random.normal(self.noise, self.noise_std),
                a_min=0.05,
                a_max=0.8,
            )
            flip_amount = int(size * noise)
            flip_include = np.random.choice(includes, flip_amount, replace=False)
            new_cube = Counter(cube)
            for to_remove in flip_include:
                new_cube[to_remove] -= 1
            flip_exclude = np.random.choice(excludes,
                                            flip_amount,
                                            p=neg_sampler,
                                            replace=False)
            for to_add in flip_exclude:
                new_cube[to_add + 1] += 1
            y_flip_include = np.random.choice(flip_include, flip_amount // 4)
            actual_cube = []
            for key, count in new_cube.items():
                actual_cube += [key for _ in range(count)]
            random.shuffle(actual_cube)
            for idx in cube:
                if idx > 0 and idx not in y_flip_include:
                    y_cubes[i, idx - 1] = 1
            processed_cubes.append(actual_cube)

        x_cubes = np.array(processed_cubes).astype(int)
        return [(x_cubes, x_regularization), (y_cubes, y_regularization)]


class CardDataGenerator(Sequence):
    def __init__(self, adj_mtx, walk_len, num_walks, batch_size, data_path=None):
        super(CardDataGenerator).__init__()
        self.num_cards = adj_mtx.shape[0]
        if data_path is not None:
            if Path(data_path).is_file():
                with open(data_path, 'r') as data_file:
                    self.data = json.load(data_file)
            else:
                self.data = self.generate_data(adj_mtx, walk_len, num_walks)
                with open(data_path, 'w') as data_file:
                    json.dump(self.data, data_file)
        else:
            self.data = self.generate_data(adj_mtx, walk_len, num_walks)
        self.batch_size = batch_size

    def generate_data(self, adj_mtx, walk_len, num_walks):
        y_mtx = adj_mtx.copy()
        np.fill_diagonal(y_mtx, 0)
        y_mtx = (y_mtx / y_mtx.sum(1)[:, None])
        positive_examples = [Counter() for _ in range(self.num_cards + 1)]
        negative_examples = [Counter() for _ in range(self.num_cards + 1)]
        for walk in range(num_walks):
            counter = 0
            examples = self.calculate_skipgrams(y_mtx, walk_len)
            for example in examples:
                counter += 1
                positive, negative = example
                for i, j in positive:
                    positive_examples[i][j] += 1
                for i, j in negative:
                    negative_examples[i][j] += 1
                if counter % 100 == 99:
                    print(counter + 1)
            print("Walk", walk, '\n')
        for positive, negative in zip(positive_examples, negative_examples):
            for key in list(positive.keys()):
                if key in negative:
                    if positive[key] > negative[key]:
                        del negative[key]
                    else:
                        del positive[key]
        for i, positive in enumerate(positive_examples):
            for j in list(positive.keys()):
                del positive_examples[j][i]
                if i in negative_examples[j]:
                    if positive[j] > negative_examples[j][i]:
                        del negative_examples[j][i]
                    else:
                        del positive_examples[i][j]
        for i, negative in enumerate(negative_examples):
            for j in list(negative.keys()):
                del negative_examples[j][i]
        return [(i, j, 1)
                for i, positive in enumerate(positive_examples)
                for j in positive.keys()] + [(i, j, 0)
                                             for i, negative in enumerate(negative_examples)
                                             for j in negative.keys()]

    def calculate_skipgrams(self, y_mtx, walk_len):
        nodes = [i for i in range(self.num_cards + 1)]
        y_mtx = np.concatenate((np.zeros((self.num_cards, 1)), y_mtx), 1)
        for i in range(self.num_cards):
            walk = [i + 1]
            cur_node = i + 1
            for _ in range(walk_len):
                sampling_table = y_mtx[cur_node - 1]
                cur_node = np.random.choice(nodes, p=sampling_table)
                walk.append(cur_node)
            couples, labels = skipgrams(walk, self.num_cards + 1, negative_samples=1.0)
            positive = []
            negative = []
            for couple, label in zip(couples, labels):
                i, j = couple
                i = int(i)
                j = int(i)
                if label == 1:
                    positive.append((i, j))
                    positive.append((j, i))
                elif label == 0:
                    negative.append((i, j))
                    negative.append((j, i))
            yield positive, negative

    def __len__(self):
        return len(self.data) / self.batch_size

    def __getitem__(self, item):
        a_s = []
        b_s = []
        y_s = []
        for i in range(self.batch_size):
            a, b, y = self.data[self.batch_size * item + i]
            a_s.append(a)
            b_s.append(b)
            y_s.append(y)
        return [(a_s, b_s), (y_s,)]

    def on_epoch_end(self):
        """
        Update indices after each epoch
        """
        np.random.shuffle(self.data)