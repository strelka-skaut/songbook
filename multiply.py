






def read_matrix():
    ...


def multiply_matrix(a, b):
    result = Matrix(a.row_count, b.col_count)

    for i in range(result.row_count):
        for j in range(result.col_count):
            result[i][j] = 0
            for k in range(a.col_count): # == b.row_count
                result[i][j] += a[i][k] * b[k][j]

