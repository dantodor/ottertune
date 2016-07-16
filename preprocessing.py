import numpy as np
from itertools import chain, combinations, combinations_with_replacement
from abc import ABCMeta, abstractmethod

from .util import NEARZERO
from common.typeutil import is_numeric_matrix, is_lexical_matrix

##==========================================================
##  Preprocessing Base Class
##==========================================================

class Preprocess(object):

    __metaclass__ = ABCMeta
    
    @abstractmethod
    def fit(self, matrix):
        pass

    @abstractmethod
    def transform(self, matrix, copy):
        pass
    
    
    def fit_transform(self, matrix, copy=True):
        self.fit(matrix)
        return self.transform(matrix, copy)

    @abstractmethod
    def reverse_transform(self, matrix, copy):
        pass
    
##==========================================================
##  Standard Normal Form
##==========================================================

class Standardize(Preprocess):

    def __init__(self, axis=0):
        assert axis >= 0
        self.axis_ = axis
        self.mean_ = None
        self.std_ = None
        
    def fit(self, matrix):
        self.mean_, self.std_ = get_mean_and_std(matrix, self.axis_)
        return self

    def transform(self, matrix, copy=True):
        assert self.mean_ is not None
        assert self.std_ is not None
        return standardize(matrix, self.mean_, self.std_, self.axis_, copy)

    def reverse_transform(self, matrix, copy=True):
        assert self.mean_ is not None
        assert self.std_ is not None
        return reverse_standardize(matrix, self.mean_, self.std_, self.axis_, copy)
        
def get_mean_and_std(matrix, axis):
    assert matrix.ndim > 0
    assert matrix.size > 0
    assert axis >= 0 and axis < matrix.ndim
    
    mmean = np.expand_dims(matrix.mean(axis=axis), axis=axis)
    mstd = np.expand_dims(matrix.std(axis=axis), axis=axis)
    #mstd[:] += NEARZERO # Protect against div0 errors
    #mstd[mstd == 0.] = 1.
    if np.any(np.abs(mstd) < NEARZERO):
        raise Exception("Standard deviation calculation has near zero values.")
    
    return mmean, mstd
    
def standardize(matrix, mmean, mstd, axis, copy=True):
    if not copy and matrix.dtype != np.dtype("float64"):
        raise TypeError("Matrix should be of type 'float64'")
    
    assert matrix.ndim > 0
    assert matrix.size > 0
    assert axis >= 0 and axis < matrix.ndim
    assert mmean is not None and mstd is not None
    
    if copy:
        matrix = (matrix - mmean) 
    else:
        matrix[:] -= mmean
    matrix[:] /= mstd

    return matrix

def reverse_standardize(matrix, mmean, mstd, axis, copy=True):
    if not copy and matrix.dtype != np.dtype("float64"):
        raise TypeError("Matrix should be of type 'float64'")
    
    assert matrix.ndim > 0
    assert matrix.size > 0
    assert axis >= 0 and axis < matrix.ndim
    assert mmean.ndim == matrix.ndim and mmean.ndim == mstd.ndim
    
    if copy:
        matrix = matrix * mstd
    else:
        matrix[:] *= mstd
    matrix[:] += mmean
    return matrix

##==========================================================
##  Bin by Deciles
##==========================================================

class Bin(Preprocess):
    
    def __init__(self, bin_start, axis=None):
        if axis is not None and \
                axis != 1 and axis != 0:
            raise NotImplementedError("Axis={} is not yet implemented"
                                      .format(axis))
        self.deciles_ = None
        self.bin_start_ = bin_start
        self.axis_ = axis
    
    def fit(self, matrix):
        if self.axis_ is None:
            self.deciles_ = get_deciles(matrix, self.axis_)
        elif self.axis_ == 0: # Bin columns
            self.deciles_ = []
            for col in matrix.T:
                self.deciles_.append(get_deciles(col, axis=None))
        elif self.axis_ == 1: # Bin rows
            self.deciles_ = []
            for row in matrix:
                self.deciles_.append(get_deciles(row, axis=None))
        return self

    def transform(self, matrix, copy=True):
        assert self.deciles_ is not None
        if self.axis_ is None:
            res = bin_by_decile(matrix, self.deciles_,
                                 self.bin_start_, self.axis_)
        elif self.axis_ == 0: # Transform columns
            columns = []
            for col, decile in zip(matrix.T, self.deciles_):
                columns.append(bin_by_decile(col, decile,
                                             self.bin_start_, axis=None))
            res = np.vstack(columns).T
        elif self.axis_ == 1: # Transform rows
            rows = []
            for row, decile in zip(matrix, self.deciles_):
                rows.append(bin_by_decile(row, decile,
                                          self.bin_start_, axis=None))
            res = np.vstack(rows)
        assert res.shape == matrix.shape
        return res

    def reverse_transform(self, matrix, copy=True):
        raise NotImplementedError("This method is not supported")

def get_deciles(matrix, axis=None):
    if axis is not None:
        raise NotImplementedError("Axis is not yet implemented")
    
    assert matrix.ndim > 0
    assert matrix.size > 0
    
    decile_range = np.arange(10,101,10)
    deciles = np.percentile(matrix, decile_range, axis=axis)
    deciles[-1] = np.Inf
    return deciles

def bin_by_decile(matrix, deciles, bin_start, axis=None):
    if axis is not None:
        raise NotImplementedError("Axis is not yet implemented")
    
    assert matrix.ndim > 0
    assert matrix.size > 0
    assert deciles is not None
    assert len(deciles) == 10
    
    binned_matrix = np.zeros_like(matrix)
    for i in range(10)[::-1]:
        decile = deciles[i]
        binned_matrix[matrix <= decile] = i + bin_start
    
    return binned_matrix

##==========================================================
##  Shuffle Indices
##==========================================================
class Shuffler(Preprocess):
    
    def __init__(self, shuffle_rows=True, shuffle_columns=False, 
                 row_indices=None, column_indices=None, seed=0):
        self.shuffle_rows_ = shuffle_rows
        self.shuffle_columns_ = shuffle_columns
        self.row_indices_ = row_indices
        self.column_indices_ = column_indices
        np.random.seed(seed)
        self.fitted_ = False
    
    def fit(self, matrix):
        if self.shuffle_rows_ and self.row_indices_ is None:
            self.row_indices_ = get_shuffle_indices(matrix.data.shape[0])
        if self.shuffle_columns_ and self.column_indices_ is None:
            self.column_indices_ = get_shuffle_indices(matrix.data.shape[1])
        self.fitted_ = True

    def transform(self, matrix, copy):
        if not self.fitted_:
            raise Exception("The fit() function must be called before transform()")
        if copy:
            matrix = matrix.copy()

        if self.shuffle_rows_:
            matrix.data = matrix.data[self.row_indices_]
            matrix.rowlabels = matrix.rowlabels[self.row_indices_]
        if self.shuffle_columns_:
            matrix.data = matrix.data[:, self.column_indices_]
            matrix.columnlabels = matrix.columnlabels[self.column_indices_]
        return matrix

    def reverse_transform(self, matrix, copy):
        if copy:
            matrix = matrix.copy()
        
        if self.shuffle_rows_:
            inverse_row_indices = np.argsort(self.row_indices_)
            matrix.data = matrix.data[inverse_row_indices]
            matrix.rowlabels = matrix.rowlabels[inverse_row_indices]
        if self.shuffle_columns_:
            reverse_column_indices = np.argsort(self.column_indices_)
            matrix.data = matrix.data[:, reverse_column_indices]
            matrix.columnlabels = matrix.columnlabels[reverse_column_indices]
        return matrix

def get_shuffle_indices(size, seed=None):
    if seed is not None:
        assert isinstance(seed, int)
        np.random.seed(seed)
    if isinstance(size, int):
        return np.random.choice(size, size, replace=False)
    else:
        indices = []
        for d in size:
            indices.append(np.random.choice(d, d, replace=False))
        return indices
    

##==========================================================
##  Polynomial Features
##==========================================================

class PolynomialFeatures(Preprocess):
    """Compute the polynomial features of the input array.
    This code was copied and modified from sklearn's
    implementation.
    """
    
    def __init__(self, degree=2, interaction_only=False, include_bias=True):
        self.degree_ = degree
        self.interaction_only_ = interaction_only
        self.include_bias_ = include_bias
        
#     @property
#     def powers_(self):
#         combinations = self._combinations(self.n_input_features_, self.degree_,
#                                           self.interaction_only_,
#                                           self.include_bias_)
#         return np.vstack(np.bincount(c, minlength=self.n_input_features_)
#                          for c in combinations)
        
    @staticmethod
    def _combinations(n_features, degree, interaction_only, include_bias):
        comb = (combinations if interaction_only else combinations_with_replacement)
        start = int(not include_bias)
        return chain.from_iterable(comb(range(n_features), i)
                                   for i in range(start, degree + 1))

    def fit(self, matrix, copy=True):
        assert matrix.ndim == 2
        assert matrix.size > 0
        
        _, n_features = matrix.shape
        combinations = self._combinations(n_features, self.degree_,
                                          self.interaction_only_,
                                          self.include_bias_)
        self.n_input_features_ = matrix.shape[1]
        self.n_output_features_ = sum(1 for _ in combinations)
        return self

    def transform(self, matrix, copy=True):
        """Transform data to polynomial features
        Parameters
        ----------
        X : array-like, shape [n_samples, n_features]
            The data to transform, row by row.
        Returns
        -------
        XP : np.ndarray shape [n_samples, NP]
            The matrix of features, where NP is the number of polynomial
            features generated from the combination of inputs.
        """
        assert matrix.ndim == 2
        assert matrix.size > 0
        
        n_samples, n_features = matrix.shape

        if n_features != self.n_input_features_:
            raise ValueError("X shape does not match training shape")

        # allocate output data
        poly_matrix = np.empty((n_samples, self.n_output_features_), dtype=matrix.dtype)

        combinations = self._combinations(n_features, self.degree_,
                                          self.interaction_only_,
                                          self.include_bias_)
        is_numeric_type = is_numeric_matrix(matrix)
        is_lexical_type = is_lexical_matrix(matrix)
        for i, c in enumerate(combinations):
            if is_numeric_type:
                poly_matrix[:, i] = matrix[:, c].prod(1)
            elif is_lexical_type:
                n_poly1_feats = n_features + int(self.include_bias_)
                if i >= n_poly1_feats:
                    x = "*".join(np.squeeze(matrix[:, c]).tolist())
                else:
                    x = "".join(np.squeeze(matrix[:, c]).tolist())
                poly_matrix[:, i] = x
            else:
                raise TypeError("Unsupported matrix type {}".format(matrix.dtype))

        return poly_matrix

    def reverse_transform(self, matrix, copy=True):
        raise NotImplementedError("This method is not supported")
    

##==========================================================
##  Testing
##==========================================================

def test_preprocess_module():
    import warnings
    from sklearn import preprocessing as skpp
    from common.optutil import arrays_share_data
    
    warnings.filterwarnings('error')
    
    assert issubclass(Standardize, Preprocess)
    assert isinstance(Standardize(), Preprocess)
    assert issubclass(Bin, Preprocess)
    assert isinstance(Bin(bin_start=1), Preprocess)
    assert issubclass(PolynomialFeatures, Preprocess)
    assert isinstance(PolynomialFeatures(), Preprocess)
    
    print ""
    print "Testing 'Standardize'..."
    x1 = np.array([[2,7,9],
                   [6,9,2],
                   [4,0,2],
                   [7,2,5]], dtype = "float64")
    
    # Tests for axis = 0
    std_norm_pp = Standardize()
    x1a0_exp_mean = np.array([[4.75, 4.5, 4.5]])
    x1a0_exp_std = np.array([[1.92029, 3.64005, 2.87228]])
    std_norm_pp.fit(x1)
    x1_scaled = std_norm_pp.transform(x1, copy = True)
    assert np.allclose(x1a0_exp_mean, std_norm_pp.mean_)
    assert np.allclose(x1a0_exp_std, std_norm_pp.std_)
    x1a0_exp = skpp.scale(x1, axis = 0)
    assert np.allclose(x1a0_exp, x1_scaled)
    assert not arrays_share_data(x1, x1_scaled)
    x2 = x1.copy()
    x2_scaled = std_norm_pp.transform(x2, copy = False)
    assert np.allclose(x1a0_exp, x2_scaled)
    assert arrays_share_data(x2, x2_scaled)
    x1_xf = std_norm_pp.reverse_transform(x1_scaled)
    assert np.allclose(x1, x1_xf)
    
    # Tests for axis = 1
    std_norm_pp = Standardize(axis = 1)
    x1a0_exp_mean = np.array([[6.], [5.66667], [2.], [4.66667]])
    x1a0_exp_std = np.array([[2.94392], [2.86744], [1.63299], [2.0548]])
    x1_scaled = std_norm_pp.fit_transform(x1, copy = True)
    assert np.allclose(x1a0_exp_mean, std_norm_pp.mean_)
    assert np.allclose(x1a0_exp_std, std_norm_pp.std_)
    x1a0_exp = skpp.scale(x1, axis = 1)
    assert np.allclose(x1a0_exp, x1_scaled)
    assert not arrays_share_data(x1, x1_scaled)
    x2 = x1.copy()
    x2_scaled = std_norm_pp.transform(x2, copy = False)
    assert np.allclose(x1a0_exp, x2_scaled)
    assert arrays_share_data(x2, x2_scaled)
    assert np.allclose(std_norm_pp.reverse_transform(x1_scaled), x1)
    
    # Test empty array
    x_empty = np.array([], dtype = "float64")
    std_norm_pp = Standardize()
    try:
        std_norm_pp.fit_transform(x_empty)
        print "Standardize: failed empty array test"
    except AssertionError:
        print "Standardize: passed empty array test"
        
        
    print "Passed all tests for 'Standardize'"
    print ""
    print "Testing 'Bin'..."
    decile_range = np.array([10, 20, 30, 40, 50, 60, 70, 80, 90, 100])
    deciles_exp = np.percentile(x1, decile_range)
    deciles_exp[-1] = np.Inf
    bin_pp = Bin(bin_start = 1)
    x1_binned = bin_pp.fit_transform(x1)
    assert np.array_equal(deciles_exp, bin_pp.deciles_)
    assert is_numeric_matrix(x1)
    assert not is_lexical_matrix(x1)
    
#     x1_binned_exp = np.array([[2,7,9],
#                               [6,9,2],
#                               [4,0,2],
#                               [7,2,5]], dtype = "float64")
    
    x1_binned_exp = np.array([[1,8,10],
                              [7,10,1],
                              [5,1,1],
                              [8,1,6]], dtype = "float64")
    assert np.array_equal(x1_binned_exp, x1_binned)
    assert not arrays_share_data(x1, x1_binned)
    
    # Test transform with floats out of original range
    x2 = np.array([-1., 6., 20.])
    x2_binned_exp = np.array([1, 7, 10])
    x2_binned = bin_pp.transform(x2)
    assert np.array_equal(x2_binned_exp, x2_binned)
    
    
    # Test empty array
    x_empty = np.array([], dtype = "float64")
    bin_pp = Bin(0)
    try:
        bin_pp.fit_transform(x_empty)
        print "Bin: failed empty array test"
    except AssertionError:
        print "Bin: passed empty array test"
        
    print "Passed all tests for 'Bin'"
    print ""
    print "Testing 'PolynomialFeatures'..."
    
    x1_poly_exp = np.array([[1,8,10,1,8,10,64,80,100],
                            [7,10,1,49,70,7,100,10,1],
                            [5,1,1,25,5,5,1,1,1],
                            [8,1,6,64,8,48,1,6,36]], dtype = "float64")
    
    x1_poly_inter_exp = np.array([[1,8,10,8,10,80],
                                  [7,10,1,70,7,10],
                                  [5,1,1,5,5,1],
                                  [8,1,6,8,48,6]], dtype = "float64")
    
    poly_pp = PolynomialFeatures(include_bias=False)
    x1_poly = poly_pp.fit_transform(x1_binned_exp)
    assert np.array_equal(x1_poly_exp, x1_poly)
    poly_pp = PolynomialFeatures(include_bias=True)
    x1_poly = poly_pp.fit_transform(x1_binned_exp)
    x1_poly_bias_exp = np.hstack([np.ones((x1_binned_exp.shape[0], 1)), x1_poly_exp])
    assert np.array_equal(x1_poly_bias_exp, x1_poly)
    poly_pp = PolynomialFeatures(include_bias=False, interaction_only=True)
    x1_poly = poly_pp.fit_transform(x1_binned_exp)
    assert np.array_equal(x1_poly_inter_exp, x1_poly)

    x_alpha = np.array([['a', 'b', 'c']], dtype=object)
    x_alpha_exp = np.array([['','a','b','c','aa','ab','ac','bb','bc','cc']])
    assert not is_numeric_matrix(x_alpha)
    assert is_lexical_matrix(x_alpha)
    poly_pp = PolynomialFeatures()
    x_alpha_poly = poly_pp.fit_transform(x_alpha)
    assert np.array_equal(x_alpha_exp, x_alpha_poly)
    
    print "Passed all tests for 'PolynomialFeatures'"
    print ""
    

if __name__ == '__main__':
    test_preprocess_module()
    
    
    


    