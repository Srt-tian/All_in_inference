# Repository rules

- Core code must remain independent of a particular model server, SDK or fixed action dimension.
- Importing modules and running the default CLI must never connect to hardware or enable motors.
- Only the runtime command owner may call robot.write or the final hold; policy workers never do so.
- Software stop must not disable torque, reset motors or open grippers. Device integration owns its explicit setup and shutdown procedures.
- Use monotonic measurement timestamps, preserve chunk time alignment and reject stale generations.
- Keep disk/network logging off the command loop. Do not hide failed driver calls or timeout faults.
- Document limitations and hardware validation status; simulated timing is not a physical robot result.
- Run the offline tests and lint for relevant changes. Do not run hardware without a current authorized experiment scope.
