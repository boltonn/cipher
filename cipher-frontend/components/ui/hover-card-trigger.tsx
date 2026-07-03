"use client"

import * as React from "react"
import { HoverCard as HoverCardPrimitive } from "radix-ui"

export function HoverCardTrigger({
  ...props
}: React.ComponentProps<typeof HoverCardPrimitive.Trigger>) {
  return (
    <HoverCardPrimitive.Trigger data-slot="hover-card-trigger" {...props} />
  )
}
