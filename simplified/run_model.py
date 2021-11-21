from distribution import create_model, prepare_data, print_solution, set_objective, solve_problem


def main():
    model_objects_path = 'model_objects/'

    model = create_model()

    objective_function = prepare_data(model, model_objects_path)
    set_objective(model, objective_function)

    solution = solve_problem(model)
    if solution:
        print_solution(model)


if __name__ == '__main__':
    main()
