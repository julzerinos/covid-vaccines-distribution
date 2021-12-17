from distribution import \
    create_model, prepare_data, print_solution, \
    save_solution, set_objective, solve_problem


def main():
    model_objects_path = 'tests/sanity_test'

    model = create_model()

    objective_function, args = prepare_data(model, model_objects_path)
    set_objective(model, objective_function)

    solution = solve_problem(model)

    model.report()
    if solution:
        [a() for a in args]
        print_solution(model)
        save_solution(solution, test_path=model_objects_path)


if __name__ == '__main__':
    main()
